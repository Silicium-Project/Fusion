//! Publisher side of the task book, run periodically: for every task this
//! node proposed, accept a claim when an attempt is open (the earliest claim
//! by its author's timestamp, then hash), ask workers again when a retry has
//! no claim yet, and finalize verified results.

use crate::storage::{TaskBookState, now_ms};
use silicium_node_core::taskbook::{DerivedTaskStatus, TaskBook, TaskEventBody};
use std::collections::BTreeSet;

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
) -> SweepOutcome {
    let me = taskbook.author();
    let now = now_ms();
    let decisions = taskbook
        .with_book(|book| {
            book.tasks_published_by(&me)
                .into_iter()
                .filter_map(|task_id| decide(book, &task_id, now).map(|d| (task_id, d)))
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
fn decide(book: &TaskBook, task_id: &str, now: u64) -> Option<Decision> {
    let state = book.task_state(task_id, now)?;
    if state.status.is_terminal() {
        return Some(Decision::Finished);
    }
    if state.status == DerivedTaskStatus::Verified {
        let attempt = state.attempts.last()?.attempt;
        return Some(Decision::Sign(TaskEventBody::TaskFinalized { attempt }));
    }
    let attempt = state.next_attempt?;
    let chosen = book
        .open_claims(task_id, now)
        .into_iter()
        .min_by(|left, right| {
            (left.issued_at_ms, &left.event_hash).cmp(&(right.issued_at_ms, &right.event_hash))
        });
    match chosen {
        Some(claim) => Some(Decision::Sign(TaskEventBody::ClaimAccepted {
            attempt,
            claim: claim.event_hash,
        })),
        None if attempt > 1 => Some(Decision::Regossip(attempt)),
        None => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::SigningKey;
    use silicium_node_core::taskbook::{EventHeader, PayloadRef, TaskEvent, TaskTerms};

    /// Signs the `sequence`-th event of `key`'s chain in `book`.
    fn emit(
        book: &mut TaskBook,
        key: &SigningKey,
        task_id: &str,
        body: TaskEventBody,
        at: u64,
    ) -> String {
        let author = TaskEvent::author_id(key);
        let header = EventHeader {
            sequence: book.next_sequence(&author),
            previous_event_hash: book.head(&author).unwrap_or_default().to_string(),
            issued_at_ms: at,
            task_id: task_id.to_string(),
        };
        let event = TaskEvent::signed(key, header, body);
        let hash = event.event_hash();
        book.append(event).unwrap();
        hash
    }

    fn proposed_task(book: &mut TaskBook, publisher: &SigningKey) -> String {
        let task_id = TaskEvent::task_id_for(&TaskEvent::author_id(publisher), "tile");
        let spec = PayloadRef {
            uri: "silicium/task/v1/tile".to_string(),
            sha256: TaskEvent::payload_hash(b"spec"),
        };
        let terms = TaskTerms {
            lease_ms: 1_000,
            max_attempts: 2,
            verifications_required: 0,
            ..TaskTerms::default()
        };
        emit(
            book,
            publisher,
            &task_id,
            TaskEventBody::TaskProposed { spec, terms },
            0,
        );
        task_id
    }

    #[test]
    fn accepts_the_earliest_claim_then_finalizes_the_result() {
        let publisher = SigningKey::from_bytes(&[1; 32]);
        let late = SigningKey::from_bytes(&[2; 32]);
        let early = SigningKey::from_bytes(&[3; 32]);
        let mut book = TaskBook::default();
        let task = proposed_task(&mut book, &publisher);
        assert!(decide(&book, &task, 0).is_none());

        emit(
            &mut book,
            &late,
            &task,
            TaskEventBody::ClaimProposed { attempt: 1 },
            20,
        );
        let early_claim = emit(
            &mut book,
            &early,
            &task,
            TaskEventBody::ClaimProposed { attempt: 1 },
            10,
        );
        let Some(Decision::Sign(accept)) = decide(&book, &task, 30) else {
            panic!("expected an acceptance");
        };
        assert_eq!(
            accept,
            TaskEventBody::ClaimAccepted {
                attempt: 1,
                claim: early_claim
            }
        );
        emit(&mut book, &publisher, &task, accept, 30);
        assert!(decide(&book, &task, 40).is_none());

        let result = PayloadRef {
            uri: "result://tile".to_string(),
            sha256: TaskEvent::payload_hash(b"r"),
        };
        emit(
            &mut book,
            &early,
            &task,
            TaskEventBody::ResultPublished {
                attempt: 1,
                result,
                milestones: Vec::new(),
            },
            50,
        );
        let Some(Decision::Sign(finalize)) = decide(&book, &task, 60) else {
            panic!("expected a finalization");
        };
        assert_eq!(finalize, TaskEventBody::TaskFinalized { attempt: 1 });
        emit(&mut book, &publisher, &task, finalize, 60);
        assert!(matches!(decide(&book, &task, 70), Some(Decision::Finished)));
    }

    #[test]
    fn a_lapsed_lease_without_new_claims_asks_for_a_retry() {
        let publisher = SigningKey::from_bytes(&[4; 32]);
        let worker = SigningKey::from_bytes(&[5; 32]);
        let mut book = TaskBook::default();
        let task = proposed_task(&mut book, &publisher);
        let claim = emit(
            &mut book,
            &worker,
            &task,
            TaskEventBody::ClaimProposed { attempt: 1 },
            0,
        );
        emit(
            &mut book,
            &publisher,
            &task,
            TaskEventBody::ClaimAccepted { attempt: 1, claim },
            0,
        );
        assert!(decide(&book, &task, 500).is_none());
        assert!(matches!(
            decide(&book, &task, 1_500),
            Some(Decision::Regossip(2))
        ));
    }
}
