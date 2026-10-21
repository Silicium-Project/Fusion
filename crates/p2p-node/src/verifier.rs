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
//! A verifier that does not have the task's model yet
//! ([`crate::workload::Workload::is_warm`]) waits [`cold_grace`] (plus a
//! delay of its own, so that cold nodes do not all start together) before
//! downloading it, and only while the result still lacks verifiers: a node
//! that already has the model (often a worker of another fragment of the
//! same job, which the publisher prefers) usually takes the check, and the
//! model is not downloaded and loaded on one more machine for a few items.
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
    collections::{BTreeMap, BTreeSet},
    hash::{Hash, Hasher},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

/// Delay before a check that could not run locally is tried again.
const RETRY_UNANSWERED_AFTER: Duration = Duration::from_secs(15);
/// Wait of a verifier without the model before it downloads it, by default.
const COLD_GRACE: Duration = Duration::from_secs(60);

/// Wait of a verifier without the model (`SILICIUM_COLD_VERIFY_GRACE_SECS`).
fn cold_grace() -> Duration {
    std::env::var("SILICIUM_COLD_VERIFY_GRACE_SECS")
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .map_or(COLD_GRACE, Duration::from_secs)
}

/// What this node already did as a verifier, by `(task id, attempt)`.
#[derive(Clone, Default)]
pub(crate) struct VerifierMemory {
    offered: Arc<Mutex<BTreeSet<(String, u32)>>>,
    started: Arc<Mutex<BTreeSet<(String, u32)>>>,
    /// When this node, without the model, first saw a result to verify.
    cold_since: Arc<Mutex<BTreeMap<(String, u32), Instant>>>,
}

impl VerifierMemory {
    /// True when this node, which does not have the model of `state`'s
    /// task, may start getting it to verify the latest result: verifier
    /// slots are still open (`slots_open`, which counts out the accepted
    /// verifiers that went silent) and the result waited `grace` plus this
    /// node's own delay (up to `grace` more, from its id and the task).
    fn cold_turn(
        &self,
        state: &DerivedTaskState,
        me: &str,
        grace: Duration,
        slots_open: u32,
    ) -> bool {
        let Some(attempt) = state.attempts.last() else {
            return false;
        };
        if attempt.verifiers.iter().any(|v| v.author == me) {
            return true;
        }
        if slots_open == 0 {
            return false;
        }
        let key = (state.task_id.clone(), attempt.attempt);
        let Ok(mut since) = self.cold_since.lock() else {
            return false;
        };
        since.retain(|_, seen| seen.elapsed() < grace * 20);
        let seen = *since.entry(key).or_insert_with(Instant::now);
        seen.elapsed() >= grace + own_delay(me, &state.task_id, grace)
    }
}

/// A delay in `0..grace` fixed by the node and the task, so that the nodes
/// without the model do not all start downloading it at once.
fn own_delay(me: &str, task_id: &str, grace: Duration) -> Duration {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    (me, task_id).hash(&mut hasher);
    let millis = grace.as_millis().max(1) as u64;
    Duration::from_millis(hasher.finish() % millis)
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
    let me = context.taskbook.author();
    let grace = cold_grace();
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
        {
            // Without the model: leave the check to a node that has it, for
            // a while (see the module documentation).
            if !workload.is_warm(&task) {
                let now = crate::storage::now_ms();
                let slots = context
                    .taskbook
                    .with_book(|book| book.verification_slots_open(&state.task_id, now))
                    .unwrap_or(0);
                if !memory.cold_turn(&state, &me, grace, slots) {
                    continue;
                }
            }
            if !workload.ensure_ready(context, &task).await {
                continue;
            }
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

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::SigningKey;
    use silicium_node_core::taskbook::{EventHeader, PayloadRef, TaskBook, TaskEvent, TaskTerms};

    fn emit(book: &mut TaskBook, key: &SigningKey, task_id: &str, body: TaskEventBody) -> String {
        let author = TaskEvent::author_id(key);
        let header = EventHeader {
            sequence: book.next_sequence(&author),
            previous_event_hash: book.head(&author).unwrap_or_default().to_string(),
            issued_at_ms: 1,
            task_id: task_id.to_string(),
        };
        let event = TaskEvent::signed(key, header, body);
        let hash = event.event_hash();
        book.append(event).unwrap();
        hash
    }

    /// A completed task awaiting one verifier, and the book.
    fn completed() -> (TaskBook, String, SigningKey) {
        let publisher = SigningKey::from_bytes(&[50; 32]);
        let worker = SigningKey::from_bytes(&[51; 32]);
        let mut book = TaskBook::default();
        let task = TaskEvent::task_id_for(&TaskEvent::author_id(&publisher), "t");
        let spec = PayloadRef {
            uri: "silicium/task/v1/t".into(),
            sha256: TaskEvent::payload_hash(b"spec"),
        };
        let terms = TaskTerms {
            lease_ms: 60_000,
            verifications_required: 1,
            ..TaskTerms::default()
        };
        emit(
            &mut book,
            &publisher,
            &task,
            TaskEventBody::TaskProposed { spec, terms },
        );
        let claim = emit(
            &mut book,
            &worker,
            &task,
            TaskEventBody::ClaimProposed { attempt: 1 },
        );
        emit(
            &mut book,
            &publisher,
            &task,
            TaskEventBody::ClaimAccepted { attempt: 1, claim },
        );
        let result = PayloadRef {
            uri: "result://t".into(),
            sha256: TaskEvent::payload_hash(b"r"),
        };
        let body = TaskEventBody::ResultPublished {
            attempt: 1,
            result,
            milestones: Vec::new(),
        };
        emit(&mut book, &worker, &task, body);
        (book, task, publisher)
    }

    #[test]
    fn a_node_without_the_model_waits_before_getting_it() {
        let (mut book, task, publisher) = completed();
        let memory = VerifierMemory::default();
        let state = book.task_state(&task, 2).unwrap();
        assert_eq!(state.status, DerivedTaskStatus::Completed);
        let slots = |book: &TaskBook, at| book.verification_slots_open(&task, at);
        assert_eq!(slots(&book, 2), 1);
        assert!(!memory.cold_turn(&state, "cold", Duration::from_secs(3600), 1));
        assert!(memory.cold_turn(&state, "cold", Duration::ZERO, 1));

        // Once a verifier is accepted, the cold node leaves it the check.
        let other = SigningKey::from_bytes(&[52; 32]);
        let offer = emit(
            &mut book,
            &other,
            &task,
            TaskEventBody::VerificationClaimed { attempt: 1 },
        );
        let accept = TaskEventBody::VerifierAccepted {
            attempt: 1,
            claim: offer,
        };
        emit(&mut book, &publisher, &task, accept);
        let state = book.task_state(&task, 3).unwrap();
        assert_eq!(slots(&book, 3), 0);
        assert!(!memory.cold_turn(&state, "cold", Duration::ZERO, 0));
        let accepted = TaskEvent::author_id(&other);
        assert!(memory.cold_turn(&state, &accepted, Duration::from_secs(3600), 0));
        // The accepted verifier went silent past its delay: the slot opens.
        assert_eq!(slots(&book, 70_000), 1);
    }

    #[test]
    fn cold_nodes_start_at_different_times() {
        let grace = Duration::from_secs(60);
        let delays: BTreeSet<_> = (0..20)
            .map(|n| own_delay(&format!("node-{n}"), "task", grace))
            .collect();
        assert!(delays.len() > 10);
        assert!(delays.iter().all(|delay| *delay < grace));
    }
}
