//! Verifier role, run periodically: for every known task whose latest result
//! awaits verification, offer to verify it; once the publisher accepts this
//! node, check the result as the task's workload defines it
//! ([`crate::workload::Workload::verify`]: re-rendered milestones for the
//! raytracer, a recomputed hash for sha256) and publish the verdict.
//!
//! Only nodes with the `verify` role take part. A node offers to verify its
//! own result only when it is the only compute / verification peer on the
//! network and the task terms allow it (lone-worker rule, see
//! [`crate::peers`]; the orchestrator/storage peer does not count).
//!
//! A verdict is only published when the check could run: if it fails
//! locally (compute daemon down, input missing), nothing is published and
//! the publisher's delay frees the slot for another verifier, instead of
//! rejecting an honest result.

use crate::{
    activity::Role, processing::NodeContext, task::NetworkTask, worker::record_task_event,
};
use silicium_node_core::taskbook::{
    DerivedTaskState, DerivedTaskStatus, ResultState, TaskEventBody,
};
use std::{
    collections::BTreeSet,
    sync::{Arc, Mutex},
};

/// Delay before a check that could not run locally is tried again.
const RETRY_UNANSWERED_AFTER: std::time::Duration = std::time::Duration::from_secs(15);

/// What this node already did as a verifier, by `(task id, attempt)`.
#[derive(Clone, Default)]
pub(crate) struct VerifierMemory {
    offered: Arc<Mutex<BTreeSet<(String, u32)>>>,
    started: Arc<Mutex<BTreeSet<(String, u32)>>>,
}

/// One verifier step for one task.
enum Step {
    Offer(u32),
    Verify(Box<Job>),
}

/// A verification this node was accepted for.
struct Job {
    task: NetworkTask,
    attempt: u32,
    result: ResultState,
    seed: String,
}

/// Runs one verifier sweep over the known tasks.
pub(crate) async fn sweep(context: &NodeContext, memory: &VerifierMemory) {
    if !context.roles.verify {
        return;
    }
    let known: Vec<NetworkTask> = context
        .known_tasks
        .lock()
        .map(|known| known.values().cloned().collect())
        .unwrap_or_default();
    for task in known {
        if !crate::workload::is_allowed(&task) {
            continue;
        }
        let Some(state) = context.taskbook.state(&task.task_id).ok().flatten() else {
            continue;
        };
        // A workload that needs a model only offers once the model is ready
        // (asking for it starts the download). Only results awaiting
        // verification ask, so finished tasks do not keep a model loaded.
        if state.status == DerivedTaskStatus::Completed
            && let Some(workload) = crate::workload::of(&task)
            && !workload.ensure_ready(context, &task).await
        {
            continue;
        }
        match next_step(context, memory, &state, task) {
            Some(Step::Offer(attempt)) => {
                let body = TaskEventBody::VerificationClaimed { attempt };
                record_task_event(context, &state.task_id, body).await;
            }
            Some(Step::Verify(job)) => {
                let context = context.clone();
                let memory = memory.clone();
                tokio::spawn(async move { verify(&context, &memory, *job).await });
            }
            None => {}
        }
    }
}

/// Decides the step for one task and records it in `memory`.
fn next_step(
    context: &NodeContext,
    memory: &VerifierMemory,
    state: &DerivedTaskState,
    task: NetworkTask,
) -> Option<Step> {
    let me = context.taskbook.author();
    let attempt = state.attempts.last()?;
    let self_check_allowed =
        state.terms.allow_self_verification && context.worker_view().no_other_worker();
    if state.status != DerivedTaskStatus::Completed
        || (attempt.claimant == me && !self_check_allowed)
    {
        return None;
    }
    let key = (state.task_id.clone(), attempt.attempt);
    let mine = attempt.verifiers.iter().find(|v| v.author == me);
    match mine {
        Some(verifier) if verifier.verdict.is_none() => {
            let result = attempt.result.clone()?;
            if !memory.started.lock().ok()?.insert(key) {
                return None;
            }
            Some(Step::Verify(Box::new(Job {
                task,
                attempt: attempt.attempt,
                result,
                seed: verifier.acceptance_event.clone(),
            })))
        }
        Some(_) => None,
        None => memory
            .offered
            .lock()
            .ok()?
            .insert(key)
            .then_some(Step::Offer(attempt.attempt)),
    }
}

/// Checks the result and publishes the verdict.
async fn verify(context: &NodeContext, memory: &VerifierMemory, job: Job) {
    context.activity.started(&job.task.task_id, Role::Verify);
    let verdict_published = check(context, &job).await;
    context
        .activity
        .finished(&job.task.task_id, Role::Verify, verdict_published);
    if !verdict_published {
        // The check could not run here (model or result not available yet):
        // a later sweep tries again, rather than leaving the verification
        // this node was accepted for unanswered.
        tokio::time::sleep(RETRY_UNANSWERED_AFTER).await;
        if let Ok(mut started) = memory.started.lock() {
            started.remove(&(job.task.task_id.clone(), job.attempt));
        }
    }
}

/// Checks the result and publishes the verdict; false when no verdict could
/// be published (the check could not run locally).
async fn check(context: &NodeContext, job: &Job) -> bool {
    let Some(workload) = crate::workload::of(&job.task) else {
        println!(
            " Unknown workload for {}; not verifying it",
            job.task.task_id
        );
        return false;
    };
    let verdict = workload
        .verify(context, &job.task, &job.result, &job.seed)
        .await;
    match verdict {
        Some(approved) => {
            publish_verdict(context, job, approved).await;
            true
        }
        None => false,
    }
}

async fn publish_verdict(context: &NodeContext, job: &Job, approved: bool) {
    println!(
        " Verdict on {} attempt {}: {approved}",
        job.task.task_id, job.attempt
    );
    let body = TaskEventBody::VerificationPublished {
        attempt: job.attempt,
        result_event: job.result.event_hash.clone(),
        approved,
    };
    record_task_event(context, &job.task.task_id, body).await;
}
