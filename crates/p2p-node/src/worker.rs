//! Worker side of the task book: claim the open attempt of a task, wait for
//! the publisher to accept this node, keep the lease alive while computing,
//! then publish the result or release the attempt.

use crate::{
    processing::{NodeContext, execute_task},
    task::NetworkTask,
};
use silicium_node_core::taskbook::{
    DerivedTaskState, PayloadRef, TaskEvent, TaskEventBody, TaskTerms,
};
use std::{
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};

/// How long to wait for the task's proposal to reach this node.
const PROPOSAL_WAIT: Duration = Duration::from_secs(10);
/// How long to wait for the publisher's decision on this node's claim.
const ACCEPT_WAIT: Duration = Duration::from_secs(30);
const POLL_INTERVAL: Duration = Duration::from_millis(250);

/// Signs, stores and queues for gossip one event of this node.
pub(crate) async fn record_task_event(context: &NodeContext, task_id: &str, body: TaskEventBody) {
    match context.taskbook.append_signed(task_id, body) {
        Ok(event) => {
            if context.tx_events.send(event).await.is_err() {
                println!(" Task book event channel closed for {task_id}");
            }
        }
        Err(err) => println!(" Failed to persist task book event for {task_id}: {err}"),
    }
}

/// Handles a task received from the network (see the module documentation).
pub(crate) async fn process_task(context: NodeContext, task: NetworkTask) {
    let task_id = task.task_id.clone();
    let Some((attempt, terms)) = open_attempt(&context, &task_id).await else {
        println!(" No open attempt for task {task_id}; not claiming it");
        return;
    };
    record_task_event(&context, &task_id, TaskEventBody::ClaimProposed { attempt }).await;
    if !wait_until_accepted(&context, &task_id, attempt).await {
        println!(" Claim on task {task_id} (attempt {attempt}) not accepted for this node");
        return;
    }
    let renewer = LeaseRenewer::start(context.clone(), task_id.clone(), attempt, terms);
    let outcome = execute_task(&context, &task).await;
    renewer.stop();
    let body = match outcome {
        Some(hash) => TaskEventBody::ResultPublished {
            attempt,
            result: PayloadRef {
                uri: format!("result://{task_id}"),
                sha256: TaskEvent::payload_hash(hash.as_bytes()),
            },
        },
        None => TaskEventBody::ClaimReleased { attempt },
    };
    record_task_event(&context, &task_id, body).await;
}

/// Current derived state of `task_id`, `None` when unknown or unreadable.
fn current_state(context: &NodeContext, task_id: &str) -> Option<DerivedTaskState> {
    context.taskbook.state(task_id).ok().flatten()
}

/// Attempt open for claims and the task terms, waiting for the proposal
/// (it may arrive after the task itself).
async fn open_attempt(context: &NodeContext, task_id: &str) -> Option<(u32, TaskTerms)> {
    let deadline = Instant::now() + PROPOSAL_WAIT;
    loop {
        if let Some(state) = current_state(context, task_id) {
            return state.next_attempt.map(|attempt| (attempt, state.terms));
        }
        if Instant::now() >= deadline {
            return None;
        }
        tokio::time::sleep(POLL_INTERVAL).await;
    }
}

/// True once the publisher accepted this node for `attempt`; false when it
/// accepted someone else, the task ended, or no decision came in time.
async fn wait_until_accepted(context: &NodeContext, task_id: &str, attempt: u32) -> bool {
    let me = context.taskbook.author();
    let deadline = Instant::now() + ACCEPT_WAIT;
    while Instant::now() < deadline {
        if let Some(state) = current_state(context, task_id) {
            if let Some(accepted) = state.attempts.get(attempt as usize - 1) {
                return accepted.claimant == me;
            }
            if state.status.is_terminal() {
                return false;
            }
        }
        tokio::time::sleep(POLL_INTERVAL).await;
    }
    false
}

/// Renews the lease of a running attempt every third of the lease, within
/// the renewals the terms allow.
struct LeaseRenewer {
    stop: Arc<AtomicBool>,
    handle: tokio::task::JoinHandle<()>,
}

impl LeaseRenewer {
    fn start(context: NodeContext, task_id: String, attempt: u32, terms: TaskTerms) -> Self {
        let stop = Arc::new(AtomicBool::new(false));
        let flag = stop.clone();
        let period = Duration::from_millis((terms.lease_ms / 3).max(1_000));
        let handle = tokio::spawn(async move {
            for _ in 0..terms.max_renewals {
                tokio::time::sleep(period).await;
                if flag.load(Ordering::Relaxed) {
                    break;
                }
                record_task_event(&context, &task_id, TaskEventBody::LeaseRenewed { attempt })
                    .await;
            }
        });
        Self { stop, handle }
    }

    fn stop(self) {
        self.stop.store(true, Ordering::Relaxed);
        self.handle.abort();
    }
}
