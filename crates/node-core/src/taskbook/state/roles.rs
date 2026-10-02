//! Who may do what: the task's publisher is the author of its proposal, and
//! only its decisions (accept a claim, finalize, cancel), replayed in the
//! order of its own chain, shape the attempts.

use super::super::{PayloadRef, TaskBook, TaskEvent, TaskEventBody, TaskTerms};
use super::attempts::{self, Draft};

/// The events of one task as seen by the derivation, equivocators removed.
pub(super) struct TaskView<'a> {
    pub(super) book: &'a TaskBook,
    pub(super) task_id: &'a str,
    pub(super) publisher: &'a str,
    pub(super) proposal_hash: &'a str,
    pub(super) spec: &'a PayloadRef,
    pub(super) terms: TaskTerms,
    /// `(hash, event)` about this task, by hash.
    pub(super) events: Vec<(&'a str, &'a TaskEvent)>,
}

/// Terminal decision of the publisher, if any.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum Terminal {
    Finalized(u32),
    Cancelled,
}

/// What the publisher's chain decided.
pub(super) struct Decisions {
    pub(super) attempts: Vec<Draft>,
    pub(super) terminal: Option<Terminal>,
}

impl<'a> TaskView<'a> {
    /// Finds the proposal of `task_id`: the publisher's earliest
    /// `TaskProposed` (only the key owning the identifier can write one).
    pub(super) fn new(book: &'a TaskBook, task_id: &'a str) -> Option<Self> {
        let events: Vec<_> = book
            .task_events(task_id)
            .into_iter()
            .filter(|(_, event)| !book.equivocators.contains(&event.author))
            .collect();
        let (proposal_hash, proposal) = events
            .iter()
            .filter(|(_, event)| {
                matches!(event.body, TaskEventBody::TaskProposed { .. })
                    && TaskEvent::owns_task(&event.author, task_id)
            })
            .min_by_key(|(_, event)| event.sequence)?;
        let TaskEventBody::TaskProposed { spec, terms } = &proposal.body else {
            return None;
        };
        Some(Self {
            book,
            task_id,
            publisher: &proposal.author,
            proposal_hash,
            spec,
            terms: *terms,
            events,
        })
    }

    /// Publisher events about this task, in the order of its chain.
    fn publisher_events(&self) -> Vec<&'a TaskEvent> {
        let mut own: Vec<_> = self
            .events
            .iter()
            .filter(|(_, event)| event.author == self.publisher)
            .map(|(_, event)| *event)
            .collect();
        own.sort_by_key(|event| event.sequence);
        own
    }

    /// Replays the publisher's decisions. Replay stops at a decision whose
    /// subject has not arrived yet (the claim it accepts, the result it
    /// finalizes): later decisions depend on it.
    pub(super) fn replay_publisher_decisions(&self) -> Decisions {
        let mut decisions = Decisions {
            attempts: Vec::new(),
            terminal: None,
        };
        for event in self.publisher_events() {
            match &event.body {
                TaskEventBody::ClaimAccepted { attempt, claim } => {
                    match self.accept(&decisions, *attempt, claim, event.issued_at_ms) {
                        Acceptance::Accepted(draft) => decisions.attempts.push(draft),
                        Acceptance::Invalid => {}
                        Acceptance::Waiting => break,
                    }
                }
                TaskEventBody::TaskFinalized { attempt } => {
                    match decisions.attempts.get(*attempt as usize - 1) {
                        Some(draft) if attempts::result_of(self, draft).is_some() => {
                            decisions.terminal = Some(Terminal::Finalized(*attempt));
                            break;
                        }
                        Some(_) => break,
                        None => {}
                    }
                }
                TaskEventBody::TaskCancelled => {
                    decisions.terminal = Some(Terminal::Cancelled);
                    break;
                }
                _ => {}
            }
        }
        decisions
    }

    /// Checks one `ClaimAccepted`: right attempt number, within the allowed
    /// attempts, naming a claim for that attempt of this task.
    fn accept(
        &self,
        decisions: &Decisions,
        attempt: u32,
        claim: &str,
        accepted_at_ms: u64,
    ) -> Acceptance {
        let expected = decisions.attempts.len() as u32 + 1;
        if attempt != expected || attempt > self.terms.max_attempts {
            return Acceptance::Invalid;
        }
        let Some(claim_event) = self.book.event(claim) else {
            return Acceptance::Waiting;
        };
        let valid = claim_event.task_id == self.task_id
            && claim_event.body == (TaskEventBody::ClaimProposed { attempt })
            && !self.book.equivocators.contains(&claim_event.author);
        if !valid {
            return Acceptance::Invalid;
        }
        Acceptance::Accepted(Draft {
            attempt,
            claimant: claim_event.author.clone(),
            claim_event: claim.to_string(),
            accepted_at_ms,
        })
    }
}

enum Acceptance {
    Accepted(Draft),
    Invalid,
    Waiting,
}
