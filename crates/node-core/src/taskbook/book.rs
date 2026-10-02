//! In-memory task book: validation of each author's chain, equivocation
//! detection, per-task limits and read accessors.
//!
//! Out-of-order arrival and backfill live in `backfill.rs`, persistence in
//! `persistence.rs`, state derivation in `state/`; they are further
//! `impl TaskBook` blocks on the type defined here.

use std::collections::{BTreeMap, BTreeSet};

use super::{TaskBookError, TaskEvent};

/// Most events one author may record about one task. An honest node needs a
/// handful per attempt; the cap stops a peer from filling every disk.
pub const MAX_EVENTS_PER_AUTHOR_PER_TASK: usize = 64;

/// What [`TaskBook::check`] decided about an event.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) enum Check {
    /// Already stored (same bytes): nothing to do.
    Duplicate,
    /// Next event of its author's chain: can be inserted.
    Next,
}

/// Verified events indexed by event hash, the head of every author's chain,
/// events waiting for a missing predecessor and the authors caught signing
/// two versions of the same event.
#[derive(Debug, Clone, Default)]
pub struct TaskBook {
    // `pub(super)`: sibling modules extend this type and need the raw maps;
    // they stay invisible outside `taskbook`.
    pub(super) events: BTreeMap<String, TaskEvent>,
    pub(super) heads: BTreeMap<String, String>,
    pub(super) by_sequence: BTreeMap<(String, u64), String>,
    pub(super) per_task: BTreeMap<(String, String), usize>,
    pub(super) pending: BTreeMap<String, BTreeMap<u64, TaskEvent>>,
    pub(super) equivocators: BTreeSet<String>,
}

impl TaskBook {
    /// Verifies `event` and appends it to its author's chain; returns its
    /// hash. The event must be the next one of its author (use
    /// [`TaskBook::receive`] for events that may arrive out of order).
    ///
    /// Re-appending an identical event is a no-op that returns the same hash.
    pub fn append(&mut self, event: TaskEvent) -> Result<String, TaskBookError> {
        event.verify()?;
        let event_hash = event.event_hash();
        if self.check(&event, &event_hash)? == Check::Next {
            self.insert(event, event_hash.clone());
        }
        Ok(event_hash)
    }

    /// Decides whether a verified event can be inserted, without changing
    /// anything except recording an equivocating author.
    pub(super) fn check(
        &mut self,
        event: &TaskEvent,
        event_hash: &str,
    ) -> Result<Check, TaskBookError> {
        if self.events.contains_key(event_hash) {
            return Ok(Check::Duplicate);
        }
        if self.equivocators.contains(&event.author) {
            return Err(TaskBookError::Equivocation(event.author.clone()));
        }
        let key = (event.author.clone(), event.sequence);
        if self.by_sequence.contains_key(&key) {
            // Same author and sequence, different bytes: a fork.
            self.equivocators.insert(event.author.clone());
            return Err(TaskBookError::Equivocation(event.author.clone()));
        }
        self.check_chain_link(event)?;
        let count_key = (event.author.clone(), event.task_id.clone());
        if self.per_task.get(&count_key).copied().unwrap_or(0) >= MAX_EVENTS_PER_AUTHOR_PER_TASK {
            return Err(TaskBookError::TooManyEvents);
        }
        Ok(Check::Next)
    }

    /// The event must follow its author's current head exactly.
    fn check_chain_link(&self, event: &TaskEvent) -> Result<(), TaskBookError> {
        match self.heads.get(&event.author) {
            None if event.sequence == 1 && event.previous_event_hash.is_empty() => Ok(()),
            None if event.sequence == 1 => Err(TaskBookError::InvalidInitialSequence),
            None => Err(TaskBookError::SequenceGap {
                author: event.author.clone(),
                expected: 1,
                actual: event.sequence,
            }),
            Some(head_hash) => {
                let head_sequence = self.events[head_hash].sequence;
                if event.sequence != head_sequence + 1 {
                    return Err(TaskBookError::SequenceGap {
                        author: event.author.clone(),
                        expected: head_sequence + 1,
                        actual: event.sequence,
                    });
                }
                if event.previous_event_hash != *head_hash {
                    return Err(TaskBookError::PreviousEventMismatch);
                }
                Ok(())
            }
        }
    }

    /// Stores an event accepted by [`TaskBook::check`].
    pub(super) fn insert(&mut self, event: TaskEvent, event_hash: String) {
        *self
            .per_task
            .entry((event.author.clone(), event.task_id.clone()))
            .or_default() += 1;
        self.by_sequence
            .insert((event.author.clone(), event.sequence), event_hash.clone());
        self.heads.insert(event.author.clone(), event_hash.clone());
        self.events.insert(event_hash, event);
    }

    /// Hash of the latest event of `author`, if any.
    pub fn head(&self, author: &str) -> Option<&str> {
        self.heads.get(author).map(String::as_str)
    }

    /// Sequence number the next event of `author` must carry (1 if none yet).
    pub fn next_sequence(&self, author: &str) -> u64 {
        self.heads
            .get(author)
            .map(|hash| self.events[hash].sequence + 1)
            .unwrap_or(1)
    }

    /// Copy of every author's head hash.
    pub fn heads(&self) -> BTreeMap<String, String> {
        self.heads.clone()
    }

    /// Event stored under `event_hash`, if any.
    pub fn event(&self, event_hash: &str) -> Option<&TaskEvent> {
        self.events.get(event_hash)
    }

    /// Authors caught signing two different events with the same sequence;
    /// their events are ignored when task states are derived.
    pub fn equivocators(&self) -> &BTreeSet<String> {
        &self.equivocators
    }

    /// Events of `author` with a sequence strictly greater than `sequence`,
    /// in sequence order (what a peer asks for to fill a gap).
    pub fn events_for_author_after(&self, author: &str, sequence: u64) -> Vec<TaskEvent> {
        self.by_sequence
            .range((author.to_string(), sequence + 1)..)
            .take_while(|((event_author, _), _)| event_author == author)
            .map(|(_, hash)| self.events[hash].clone())
            .collect()
    }

    /// All stored events, ordered by event hash.
    pub fn events(&self) -> impl Iterator<Item = &TaskEvent> {
        self.events.values()
    }

    /// Stored events about `task_id` with their hashes, ordered by hash.
    pub(super) fn task_events(&self, task_id: &str) -> Vec<(&str, &TaskEvent)> {
        self.events
            .iter()
            .filter(|(_, event)| event.task_id == task_id)
            .map(|(hash, event)| (hash.as_str(), event))
            .collect()
    }
}
