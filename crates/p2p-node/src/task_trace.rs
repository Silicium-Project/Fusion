//! Signed task-book trace of one task, for the BackEnd's blockchain proof.
//!
//! Every lifecycle step of a task is an Ed25519-signed task-book event. This
//! module picks out the ones a user needs to check who did the work: the
//! publisher's proposal, the worker's accepted claim, the result it published
//! and the verdicts of the verifiers the publisher accepted. The BackEnd
//! hashes these traces into a Merkle tree and anchors its root on Solana, so
//! a user can later prove that a given task was part of the anchored job.
//!
//! Authors are task-book author ids (hex Ed25519 public keys), not libp2p
//! peer ids: they are what signs the events.

use serde::Serialize;
use silicium_node_core::taskbook::{AttemptState, DerivedTaskState};

/// Trace of the attempt that produced a task's current (or final) result.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub(crate) struct TaskTrace {
    /// Author id of the node that proposed the task (the orchestrator).
    pub(crate) publisher: String,
    /// Hash of the signed `TaskProposed` event.
    pub(crate) proposal_event: String,
    /// Hash of the task specification the proposal commits to.
    pub(crate) spec_sha256: String,
    /// Attempt number traced (the finalized one when the task is done).
    pub(crate) attempt: u32,
    /// Author id of the worker that computed the result.
    pub(crate) worker: String,
    /// Hash of the worker's signed claim event.
    pub(crate) claim_event: String,
    /// Hash of the worker's signed result event (empty before a result).
    pub(crate) result_event: String,
    /// SHA-256 of the result content (empty before a result).
    pub(crate) result_sha256: String,
    /// Verifiers accepted for the attempt, with their verdict.
    pub(crate) verifiers: Vec<VerifierTrace>,
    /// True when the publisher accepted this attempt's result.
    pub(crate) finalized: bool,
}

/// One verifier of a traced attempt.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub(crate) struct VerifierTrace {
    /// Author id of the verifier.
    pub(crate) author: String,
    /// `Some(true)` approved, `Some(false)` rejected, `None` pending.
    pub(crate) verdict: Option<bool>,
    /// Hash of the signed verification event, once given.
    pub(crate) verification_event: String,
    /// True when the verifier checked its own result (single-worker network).
    pub(crate) self_verification: bool,
}

/// Trace of the attempt that matters for `state`, or `None` before any claim.
///
/// The finalized attempt wins; otherwise the latest one, so a running job
/// already shows who is working on each task.
pub(crate) fn trace_of(state: &DerivedTaskState) -> Option<TaskTrace> {
    let attempt = state
        .finalized_attempt
        .and_then(|number| state.attempts.iter().find(|item| item.attempt == number))
        .or_else(|| state.attempts.last())?;
    let result = attempt.result.as_ref();
    Some(TaskTrace {
        publisher: state.publisher.clone(),
        proposal_event: state.proposal_event.clone(),
        spec_sha256: state.spec.sha256.clone(),
        attempt: attempt.attempt,
        worker: attempt.claimant.clone(),
        claim_event: attempt.claim_event.clone(),
        result_event: result
            .map(|item| item.event_hash.clone())
            .unwrap_or_default(),
        result_sha256: result
            .map(|item| item.result.sha256.clone())
            .unwrap_or_default(),
        verifiers: verifier_traces(attempt),
        finalized: state.finalized_attempt == Some(attempt.attempt),
    })
}

/// Verifiers of `attempt` with the hash of the event carrying their verdict.
fn verifier_traces(attempt: &AttemptState) -> Vec<VerifierTrace> {
    let verdict_events: Vec<&(String, String)> = attempt
        .result
        .iter()
        .flat_map(|result| result.approvals.iter().chain(result.rejections.iter()))
        .collect();
    attempt
        .verifiers
        .iter()
        .map(|verifier| VerifierTrace {
            author: verifier.author.clone(),
            verdict: verifier.verdict,
            verification_event: verdict_events
                .iter()
                .find(|(_, author)| author == &verifier.author)
                .map(|(event, _)| event.clone())
                .unwrap_or_default(),
            self_verification: verifier.author == attempt.claimant,
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use silicium_node_core::taskbook::{
        DerivedTaskStatus, PayloadRef, ResultState, TaskTerms, VerifierState,
    };

    fn payload(sha: &str) -> PayloadRef {
        PayloadRef {
            uri: format!("result://{sha}"),
            sha256: sha.to_string(),
        }
    }

    fn attempt(number: u32, claimant: &str, with_result: bool) -> AttemptState {
        AttemptState {
            attempt: number,
            claimant: claimant.to_string(),
            claim_event: format!("claim-{number}"),
            accepted_at_ms: 0,
            renewals: 0,
            lease_expires_at_ms: 0,
            released: false,
            verifiers: vec![VerifierState {
                author: "verifier".to_string(),
                acceptance_event: format!("accept-{number}"),
                accepted_at_ms: 0,
                verdict: with_result.then_some(true),
            }],
            result: with_result.then(|| ResultState {
                event_hash: format!("result-{number}"),
                result: payload(&format!("sha-{number}")),
                milestones: Vec::new(),
                approvals: vec![(format!("verdict-{number}"), "verifier".to_string())],
                rejections: Vec::new(),
            }),
        }
    }

    fn state(attempts: Vec<AttemptState>, finalized: Option<u32>) -> DerivedTaskState {
        DerivedTaskState {
            task_id: "task".to_string(),
            publisher: "publisher".to_string(),
            proposal_event: "proposal".to_string(),
            spec: payload("spec"),
            terms: TaskTerms::default(),
            status: if finalized.is_some() {
                DerivedTaskStatus::Finalized
            } else {
                DerivedTaskStatus::Claimed
            },
            attempts,
            next_attempt: None,
            finalized_attempt: finalized,
        }
    }

    #[test]
    fn no_trace_before_a_claim() {
        assert_eq!(trace_of(&state(Vec::new(), None)), None);
    }

    #[test]
    fn finalized_attempt_is_traced_with_its_verdicts() {
        let trace = trace_of(&state(
            vec![attempt(1, "good", true), attempt(2, "late", false)],
            Some(1),
        ))
        .expect("trace");
        assert_eq!(trace.worker, "good");
        assert_eq!(trace.result_event, "result-1");
        assert_eq!(trace.result_sha256, "sha-1");
        assert!(trace.finalized);
        assert_eq!(trace.verifiers[0].verdict, Some(true));
        assert_eq!(trace.verifiers[0].verification_event, "verdict-1");
        assert!(!trace.verifiers[0].self_verification);
    }

    #[test]
    fn running_task_traces_its_latest_attempt() {
        let trace = trace_of(&state(vec![attempt(1, "worker", false)], None)).expect("trace");
        assert_eq!(trace.worker, "worker");
        assert!(trace.result_event.is_empty());
        assert_eq!(trace.verifiers[0].verdict, None);
        assert!(!trace.finalized);
    }

    #[test]
    fn single_worker_self_verification_is_flagged() {
        let mut only = attempt(1, "verifier", true);
        only.claimant = "verifier".to_string();
        let trace = trace_of(&state(vec![only], Some(1))).expect("trace");
        assert!(trace.verifiers[0].self_verification);
    }
}
