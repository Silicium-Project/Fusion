//! Cross-peer verification: a peer offers to verify a result
//! (`VerificationClaimed`), the publisher accepts it (`VerifierAccepted`), and
//! only accepted verifiers' verdicts count. The milestones to re-render are
//! drawn from the publisher's acceptance hash, which the claimant could not
//! know when it committed to its result.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use super::super::{MilestoneSample, TaskBook, TaskEvent, TaskEventBody, hex::sha256_hex};
use super::attempts::Draft;
use super::roles::{Acceptance, TaskView};
use super::{DerivedTaskStatus, VerifierState};

/// Verdicts as `(verification event hash, verifier)`.
pub(super) type Verdicts = Vec<(String, String)>;

/// A verifier accepted by the publisher, before its verdict is read.
#[derive(Debug, Clone)]
pub(super) struct VerifierDraft {
    pub(super) author: String,
    pub(super) acceptance_event: String,
    pub(super) accepted_at_ms: u64,
}

/// Checks one `VerifierAccepted`: it names a verification offer for that
/// attempt of this task, from someone other than the claimant, not already
/// accepted.
pub(super) fn accept_verifier(
    view: &TaskView,
    draft: &Draft,
    claim: &str,
    acceptance: &TaskEvent,
) -> Acceptance<VerifierDraft> {
    let Some(offer) = view.book.event(claim) else {
        return Acceptance::Waiting;
    };
    let valid = offer.task_id == view.task_id
        && offer.body
            == (TaskEventBody::VerificationClaimed {
                attempt: draft.attempt,
            })
        && offer.author != draft.claimant
        && !view.book.equivocators.contains(&offer.author)
        && !draft.verifiers.iter().any(|v| v.author == offer.author);
    if !valid {
        return Acceptance::Invalid;
    }
    Acceptance::Accepted(VerifierDraft {
        author: offer.author.clone(),
        acceptance_event: acceptance.event_hash(),
        accepted_at_ms: acceptance.issued_at_ms,
    })
}

/// Earliest verdict of each accepted verifier on `result_hash`.
fn first_verdicts<'a>(
    view: &'a TaskView,
    draft: &Draft,
    result_hash: &str,
) -> BTreeMap<&'a str, (&'a str, &'a TaskEvent)> {
    let mut first: BTreeMap<&str, (&str, &TaskEvent)> = BTreeMap::new();
    for (hash, event) in &view.events {
        let TaskEventBody::VerificationPublished {
            attempt,
            result_event,
            ..
        } = &event.body
        else {
            continue;
        };
        let accepted = draft.verifiers.iter().any(|v| v.author == event.author);
        if *attempt != draft.attempt || result_event != result_hash || !accepted {
            continue;
        }
        let entry = first.entry(&event.author).or_insert((hash, event));
        if event.sequence < entry.1.sequence {
            *entry = (hash, event);
        }
    }
    first
}

/// Approvals and rejections of the accepted verifiers, each sorted by hash.
pub(super) fn verdicts(view: &TaskView, draft: &Draft, result_hash: &str) -> (Verdicts, Verdicts) {
    let mut approvals = Vec::new();
    let mut rejections = Vec::new();
    for (author, (hash, event)) in first_verdicts(view, draft, result_hash) {
        let pair = (hash.to_string(), author.to_string());
        match event.body {
            TaskEventBody::VerificationPublished { approved: true, .. } => approvals.push(pair),
            _ => rejections.push(pair),
        }
    }
    approvals.sort();
    rejections.sort();
    (approvals, rejections)
}

/// Accepted verifiers of an attempt with their verdict on its result, if any.
pub(super) fn verifier_states(view: &TaskView, draft: &Draft) -> Vec<VerifierState> {
    let result_hash = super::attempts::result_of(view, draft).map(|result| result.event_hash);
    let given = result_hash
        .as_deref()
        .map(|hash| first_verdicts(view, draft, hash))
        .unwrap_or_default();
    draft
        .verifiers
        .iter()
        .map(|verifier| VerifierState {
            author: verifier.author.clone(),
            acceptance_event: verifier.acceptance_event.clone(),
            accepted_at_ms: verifier.accepted_at_ms,
            verdict: given.get(verifier.author.as_str()).map(|(_, event)| {
                matches!(
                    event.body,
                    TaskEventBody::VerificationPublished { approved: true, .. }
                )
            }),
        })
        .collect()
}

/// A verification offer waiting for the publisher's decision.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OpenVerification {
    pub event_hash: String,
    pub author: String,
    pub issued_at_ms: u64,
}

impl TaskBook {
    /// Verifier slots the publisher may still fill for the latest attempt of
    /// `task_id` at `now_ms`: required approvals minus approvals received and
    /// minus accepted verifiers still within their delay (one lease).
    pub fn verification_slots_open(&self, task_id: &str, now_ms: u64) -> u32 {
        let Some(state) = self.task_state(task_id, now_ms) else {
            return 0;
        };
        let Some(attempt) = state.attempts.last() else {
            return 0;
        };
        if state.status != DerivedTaskStatus::Completed {
            return 0;
        }
        let waiting = attempt
            .verifiers
            .iter()
            .filter(|v| {
                v.verdict.is_none()
                    && now_ms <= v.accepted_at_ms.saturating_add(state.terms.lease_ms)
            })
            .count();
        let approvals = attempt.result.as_ref().map_or(0, |r| r.approvals.len());
        (state.terms.verifications_required as usize).saturating_sub(approvals + waiting) as u32
    }

    /// Verification offers for the latest attempt of `task_id`: one per
    /// author (its earliest), never the claimant or an accepted verifier,
    /// ordered by event hash. Empty unless the attempt awaits verification.
    pub fn open_verifications(&self, task_id: &str, now_ms: u64) -> Vec<OpenVerification> {
        let Some(state) = self.task_state(task_id, now_ms) else {
            return Vec::new();
        };
        let Some(attempt) = state.attempts.last() else {
            return Vec::new();
        };
        if state.status != DerivedTaskStatus::Completed {
            return Vec::new();
        }
        let excluded: Vec<&str> = std::iter::once(attempt.claimant.as_str())
            .chain(attempt.verifiers.iter().map(|v| v.author.as_str()))
            .collect();
        let wanted = TaskEventBody::VerificationClaimed {
            attempt: attempt.attempt,
        };
        let mut by_author: BTreeMap<&str, &TaskEvent> = BTreeMap::new();
        for (_, event) in self.task_events(task_id) {
            if event.body != wanted
                || excluded.contains(&event.author.as_str())
                || self.equivocators.contains(&event.author)
            {
                continue;
            }
            let entry = by_author.entry(&event.author).or_insert(event);
            if event.sequence < entry.sequence {
                *entry = event;
            }
        }
        let mut offers: Vec<OpenVerification> = by_author
            .into_values()
            .map(|event| OpenVerification {
                event_hash: event.event_hash(),
                author: event.author.clone(),
                issued_at_ms: event.issued_at_ms,
            })
            .collect();
        offers.sort_by(|left, right| left.event_hash.cmp(&right.event_hash));
        offers
    }
}

/// Number of milestones a verifier re-renders: a fifth of them, between 1
/// and 8 (0 when there is none).
pub fn verification_sample_count(milestones: usize) -> usize {
    if milestones == 0 {
        return 0;
    }
    milestones.div_ceil(5).clamp(1, 8).min(milestones)
}

/// Milestones to re-render, drawn from `seed` (the verifier's acceptance
/// hash): ordered by SHA-256 of `seed:index`, first `count` taken.
pub fn sample_milestones<'a>(
    milestones: &'a [MilestoneSample],
    seed: &str,
    count: usize,
) -> Vec<&'a MilestoneSample> {
    let mut ranked: Vec<(String, &MilestoneSample)> = milestones
        .iter()
        .map(|milestone| {
            (
                sha256_hex(format!("{seed}:{}", milestone.index).as_bytes()),
                milestone,
            )
        })
        .collect();
    ranked.sort_by(|left, right| left.0.cmp(&right.0));
    ranked
        .into_iter()
        .take(count)
        .map(|(_, milestone)| milestone)
        .collect()
}
