//! Publisher side of the task book, run periodically: for every task this
//! node proposed, accept a claim when an attempt is open and a verifier when
//! a result needs one, ask workers again when a retry has no claim yet, and
//! finalize verified results.
//!
//! Offers are ranked by the author's reputation derived from the book
//! (finalized vs failed attempts), then by age. The claimant's offer to
//! verify itself is only accepted when this node has no connected peer
//! (single-node network) and the task terms allow it.

use crate::storage::{TaskBookState, now_ms};
use silicium_node_core::taskbook::{AuthorRecord, DerivedTaskStatus, TaskBook, TaskEventBody};
use std::collections::{BTreeMap, BTreeSet};

/// Inputs shared by the decisions of one sweep.
struct SweepView<'a> {
    book: &'a TaskBook,
    now: u64,
    records: BTreeMap<String, AuthorRecord>,
    alone: bool,
}

impl SweepView<'_> {
    fn score(&self, author: &str) -> f64 {
        self.records
            .get(author)
            .copied()
            .unwrap_or_default()
            .score()
    }

    /// Best offer: highest reputation, then oldest, then smallest hash.
    fn best<'o, T>(&self, offers: &'o [T], key: impl Fn(&T) -> (&str, u64, &str)) -> Option<&'o T> {
        offers.iter().min_by(|left, right| {
            let (left_author, left_at, left_hash) = key(left);
            let (right_author, right_at, right_hash) = key(right);
            self.score(right_author)
                .total_cmp(&self.score(left_author))
                .then(left_at.cmp(&right_at))
                .then(left_hash.cmp(right_hash))
        })
    }
}

/// What the sweep asks the event loop to do.
#[derive(Debug, Default)]
pub(crate) struct SweepOutcome {
    /// Events signed by this node, to gossip.
    pub(crate) events: Vec<silicium_node_core::taskbook::TaskEvent>,
    /// Tasks to gossip again (a retry is open and nobody claimed it yet).
    pub(crate) regossip: Vec<String>,
    /// Tasks that reached a terminal state.
    pub(crate) finished: Vec<String>,
}

/// One decision for one task.
enum Decision {
    Sign(TaskEventBody),
    Regossip(u32),
    Finished,
}

/// Runs one sweep. `regossiped` remembers `(task, attempt)` already gossiped
/// again, so each retry is announced once.
pub(crate) fn sweep(
    taskbook: &TaskBookState,
    regossiped: &mut BTreeSet<(String, u32)>,
    alone: bool,
) -> SweepOutcome {
    let me = taskbook.author();
    let now = now_ms();
    let decisions = taskbook
        .with_book(|book| {
            let view = SweepView {
                book,
                now,
                records: book.author_records(now),
                alone,
            };
            book.tasks_published_by(&me)
                .into_iter()
                .filter_map(|task_id| decide(&view, &task_id).map(|d| (task_id, d)))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();

    let mut outcome = SweepOutcome::default();
    for (task_id, decision) in decisions {
        match decision {
            Decision::Sign(body) => match taskbook.append_signed(&task_id, body) {
                Ok(event) => outcome.events.push(event),
                Err(err) => println!(" Publisher could not sign for {task_id}: {err}"),
            },
            Decision::Regossip(attempt) => {
                if regossiped.insert((task_id.clone(), attempt)) {
                    outcome.regossip.push(task_id);
                }
            }
            Decision::Finished => outcome.finished.push(task_id),
        }
    }
    outcome
}

/// The publisher's next move for one of its tasks, if any.
fn decide(view: &SweepView, task_id: &str) -> Option<Decision> {
    let state = view.book.task_state(task_id, view.now)?;
    if state.status.is_terminal() {
        return Some(Decision::Finished);
    }
    if state.status == DerivedTaskStatus::Verified {
        let attempt = state.attempts.last()?.attempt;
        return Some(Decision::Sign(TaskEventBody::TaskFinalized { attempt }));
    }
    if state.status == DerivedTaskStatus::Completed {
        return accept_verifier(view, task_id, state.attempts.last()?.attempt);
    }
    let attempt = state.next_attempt?;
    let claims = view.book.open_claims(task_id, view.now);
    let chosen = view.best(&claims, |c| (&c.author, c.issued_at_ms, &c.event_hash));
    match chosen {
        Some(claim) => Some(Decision::Sign(TaskEventBody::ClaimAccepted {
            attempt,
            claim: claim.event_hash.clone(),
        })),
        None if attempt > 1 => Some(Decision::Regossip(attempt)),
        None => None,
    }
}

/// Accepts the best verification offer while a verifier slot is open; the
/// claimant's own offer only when this node is alone.
fn accept_verifier(view: &SweepView, task_id: &str, attempt: u32) -> Option<Decision> {
    if view.book.verification_slots_open(task_id, view.now) == 0 {
        return None;
    }
    let offers = view.book.open_verifications(task_id, view.now);
    let independent: Vec<_> = offers.iter().filter(|o| !o.self_offer).cloned().collect();
    let pool = if independent.is_empty() && view.alone {
        offers
    } else {
        independent
    };
    let offer = view.best(&pool, |o| (&o.author, o.issued_at_ms, &o.event_hash))?;
    Some(Decision::Sign(TaskEventBody::VerifierAccepted {
        attempt,
        claim: offer.event_hash.clone(),
    }))
}

#[cfg(test)]
mod tests;
