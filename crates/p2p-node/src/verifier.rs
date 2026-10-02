//! Verifier role, run periodically: for every known task whose latest result
//! awaits verification, offer to verify it (never for a result of this
//! node); once the publisher accepts this node, re-render the milestones
//! drawn from the acceptance hash and publish the verdict.
//!
//! A verdict is only published when every sampled block could be rendered:
//! if the local compute daemon fails, nothing is published and the
//! publisher's delay frees the slot for another verifier, instead of
//! rejecting an honest result.

use crate::{
    processing::{NodeContext, render_region},
    task::NetworkTask,
    worker::record_task_event,
};
use silicium_node_core::taskbook::{
    DerivedTaskState, DerivedTaskStatus, ResultState, TaskEventBody, sample_milestones,
    verification_sample_count,
};
use std::{
    collections::BTreeSet,
    sync::{Arc, Mutex},
};

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
    let known: Vec<NetworkTask> = context
        .known_tasks
        .lock()
        .map(|known| known.values().cloned().collect())
        .unwrap_or_default();
    for task in known {
        let Some(state) = context.taskbook.state(&task.task_id).ok().flatten() else {
            continue;
        };
        match next_step(context, memory, &state, task) {
            Some(Step::Offer(attempt)) => {
                let body = TaskEventBody::VerificationClaimed { attempt };
                record_task_event(context, &state.task_id, body).await;
            }
            Some(Step::Verify(job)) => {
                let context = context.clone();
                tokio::spawn(async move { verify(&context, *job).await });
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
    if state.status != DerivedTaskStatus::Completed || attempt.claimant == me {
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

/// Re-renders the sampled milestones and publishes the verdict.
async fn verify(context: &NodeContext, job: Job) {
    let milestones = &job.result.milestones;
    let sample = sample_milestones(
        milestones,
        &job.seed,
        verification_sample_count(milestones.len()),
    );
    // A result without commitment cannot be checked: it is rejected.
    let mut approved = !sample.is_empty();
    for milestone in sample {
        let output = format!(
            "verify/{}/attempt-{}-block-{}.ppm",
            job.task.task_id.replace('/', "_"),
            job.attempt,
            milestone.index
        );
        match render_region(context, &job.task, &output, milestone).await {
            Some(hash) if hash == milestone.pixel_sha256 => {}
            Some(_) => {
                approved = false;
                break;
            }
            None => {
                println!(
                    " Could not render a block of {}; no verdict published",
                    job.task.task_id
                );
                return;
            }
        }
    }
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
