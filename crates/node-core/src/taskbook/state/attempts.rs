//! What happened inside each accepted attempt — lease renewals, release,
//! result, verdicts — counting only events from the authors allowed to send
//! them, and the resulting task status.

use super::super::{TaskEvent, TaskEventBody};
use super::roles::{Decisions, TaskView, Terminal};
use super::verification::{self, VerifierDraft};
use super::{AttemptState, DerivedTaskState, DerivedTaskStatus, ResultState};

/// An attempt accepted by the publisher, before its details are read.
#[derive(Debug, Clone)]
pub(super) struct Draft {
    pub(super) attempt: u32,
    pub(super) claimant: String,
    pub(super) claim_event: String,
    pub(super) accepted_at_ms: u64,
    pub(super) verifiers: Vec<VerifierDraft>,
}

/// Builds the derived state from the publisher's decisions.
pub(super) fn summarize(view: &TaskView, decisions: Decisions, now_ms: u64) -> DerivedTaskState {
    let attempts: Vec<AttemptState> = decisions
        .attempts
        .iter()
        .map(|draft| detail(view, draft))
        .collect();
    let (status, next_attempt, finalized_attempt) =
        status_of(view, &attempts, decisions.terminal, now_ms);
    DerivedTaskState {
        task_id: view.task_id.to_string(),
        publisher: view.publisher.to_string(),
        proposal_event: view.proposal_hash.to_string(),
        spec: view.spec.clone(),
        terms: view.terms,
        status,
        attempts,
        next_attempt,
        finalized_attempt,
    }
}

/// Status, attempt open for claims, finalized attempt.
fn status_of(
    view: &TaskView,
    attempts: &[AttemptState],
    terminal: Option<Terminal>,
    now_ms: u64,
) -> (DerivedTaskStatus, Option<u32>, Option<u32>) {
    match terminal {
        Some(Terminal::Finalized(attempt)) => {
            return (DerivedTaskStatus::Finalized, None, Some(attempt));
        }
        Some(Terminal::Cancelled) => return (DerivedTaskStatus::Cancelled, None, None),
        None => {}
    }
    let Some(last) = attempts.last() else {
        return (DerivedTaskStatus::Open, Some(1), None);
    };
    let status = attempt_status(view, last, now_ms);
    if !status.is_failed_attempt() {
        return (status, None, None);
    }
    if last.attempt < view.terms.max_attempts {
        (status, Some(last.attempt + 1), None)
    } else {
        (DerivedTaskStatus::Failed, None, None)
    }
}

/// Status of one attempt: a result wins over an expired lease or a release
/// (a late result still counts while no newer attempt was accepted).
fn attempt_status(view: &TaskView, attempt: &AttemptState, now_ms: u64) -> DerivedTaskStatus {
    if let Some(result) = &attempt.result {
        if !result.rejections.is_empty() {
            DerivedTaskStatus::Rejected
        } else if result.approvals.len() >= view.terms.verifications_required as usize {
            DerivedTaskStatus::Verified
        } else {
            DerivedTaskStatus::Completed
        }
    } else if attempt.released {
        DerivedTaskStatus::Released
    } else if now_ms > attempt.lease_expires_at_ms {
        DerivedTaskStatus::LeaseExpired
    } else {
        DerivedTaskStatus::Claimed
    }
}

/// Reads renewals, release, result and verdicts of an accepted attempt.
fn detail(view: &TaskView, draft: &Draft) -> AttemptState {
    let renewals = claimant_events(view, draft)
        .filter(|event| {
            event.body
                == (TaskEventBody::LeaseRenewed {
                    attempt: draft.attempt,
                })
        })
        .count()
        .min(view.terms.max_renewals as usize) as u32;
    let lease = view.terms.lease_ms.saturating_mul(u64::from(renewals) + 1);
    AttemptState {
        attempt: draft.attempt,
        claimant: draft.claimant.clone(),
        claim_event: draft.claim_event.clone(),
        accepted_at_ms: draft.accepted_at_ms,
        renewals,
        lease_expires_at_ms: draft.accepted_at_ms.saturating_add(lease),
        released: claimant_events(view, draft).any(|event| {
            event.body
                == (TaskEventBody::ClaimReleased {
                    attempt: draft.attempt,
                })
        }),
        verifiers: verification::verifier_states(view, draft),
        result: result_of(view, draft),
    }
}

/// Events about the task written by the attempt's claimant.
fn claimant_events<'a>(
    view: &'a TaskView,
    draft: &'a Draft,
) -> impl Iterator<Item = &'a TaskEvent> + 'a {
    view.events
        .iter()
        .map(|(_, event)| *event)
        .filter(move |event| event.author == draft.claimant)
}

/// The claimant's first result for the attempt, with the verdicts of its
/// accepted verifiers.
pub(super) fn result_of(view: &TaskView, draft: &Draft) -> Option<ResultState> {
    let (hash, event) = view
        .events
        .iter()
        .filter(|(_, event)| {
            event.author == draft.claimant
                && matches!(event.body, TaskEventBody::ResultPublished { attempt, .. } if attempt == draft.attempt)
        })
        .min_by_key(|(_, event)| event.sequence)?;
    let TaskEventBody::ResultPublished {
        result, milestones, ..
    } = &event.body
    else {
        return None;
    };
    let (approvals, rejections) = verification::verdicts(view, draft, hash);
    Some(ResultState {
        event_hash: hash.to_string(),
        result: result.clone(),
        milestones: milestones.clone(),
        approvals,
        rejections,
    })
}
