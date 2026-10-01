//! In-memory task book: validation of each author's chain, merging of remote
//! events and read accessors.
//!
//! Persistence lives in `persistence.rs`, state derivation in `state.rs`;
//! both are further `impl TaskBook` blocks on the type defined here.

use std::collections::BTreeMap;

use super::{TaskBookError, TaskEvent, hex::decode_fixed};

/// Set of verified events indexed by event hash, plus the latest event hash
/// (head) of every author.
#[derive(Debug, Clone, Default)]
pub struct TaskBook {
    // `pub(super)`: the sibling modules `persistence` and `state` extend this
    // type and need the raw maps; they stay invisible outside `taskbook`.
    pub(super) events: BTreeMap<String, TaskEvent>,
    pub(super) heads: BTreeMap<String, String>,
}

impl TaskBook {
    /// Verifies `event` and appends it to its author's chain; returns its
    /// hash.
    ///
    /// Re-appending an identical event is a no-op that returns the same hash.
    pub fn append(&mut self, event: TaskEvent) -> Result<String, TaskBookError> {
        event.verify_signature()?;
        if decode_fixed::<32>(&event.payload_hash).is_none() {
            return Err(TaskBookError::InvalidHash);
        }

        let event_hash = event.event_hash();
        if let Some(existing) = self.events.get(&event_hash) {
            if existing == &event {
                return Ok(event_hash);
            }
            return Err(TaskBookError::ConflictingEvent);
        }

        let current_head = self.heads.get(&event.author);
        match (event.sequence, current_head) {
            (1, None) if event.previous_event_hash.is_empty() => {}
            (1, Some(_)) => return Err(TaskBookError::ConflictingEvent),
            (1, None) => return Err(TaskBookError::InvalidInitialSequence),
            (sequence, Some(head_hash)) => {
                let head = self
                    .events
                    .get(head_hash)
                    .ok_or(TaskBookError::PreviousEventMismatch)?;
                if sequence != head.sequence + 1 {
                    return Err(TaskBookError::SequenceGap {
                        author: event.author.clone(),
                        expected: head.sequence + 1,
                        actual: sequence,
                    });
                }
                if event.previous_event_hash != *head_hash {
                    return Err(TaskBookError::PreviousEventMismatch);
                }
            }
            (sequence, None) => {
                return Err(TaskBookError::SequenceGap {
                    author: event.author.clone(),
                    expected: 1,
                    actual: sequence,
                });
            }
        }

        self.events.insert(event_hash.clone(), event.clone());
        self.heads.insert(event.author, event_hash.clone());
        Ok(event_hash)
    }

    /// Appends a batch of events (e.g. received from a peer); returns how many
    /// were new.
    ///
    /// Events are sorted by (author, sequence, hash) first so that the result
    /// does not depend on the order they arrived in. Stops at the first
    /// invalid event; the events appended before it are kept.
    pub fn merge(
        &mut self,
        events: impl IntoIterator<Item = TaskEvent>,
    ) -> Result<usize, TaskBookError> {
        let mut events: Vec<_> = events.into_iter().collect();
        events.sort_by_key(|event| (event.author.clone(), event.sequence, event.event_hash()));
        let before = self.events.len();
        for event in events {
            self.append(event)?;
        }
        Ok(self.events.len() - before)
    }

    /// Hash of the latest event of `author`, if any.
    pub fn head(&self, author: &str) -> Option<&str> {
        self.heads.get(author).map(String::as_str)
    }

    /// Sequence number the next event of `author` must carry (1 if none yet).
    pub fn next_sequence(&self, author: &str) -> u64 {
        self.heads
            .get(author)
            .and_then(|hash| self.events.get(hash))
            .map(|event| event.sequence + 1)
            .unwrap_or(1)
    }

    /// Copy of every author's head hash.
    pub fn heads(&self) -> BTreeMap<String, String> {
        self.heads.clone()
    }

    /// Events of `author` with a sequence strictly greater than `sequence`,
    /// in sequence order.
    pub fn events_for_author_after(&self, author: &str, sequence: u64) -> Vec<TaskEvent> {
        let mut events: Vec<_> = self
            .events
            .values()
            .filter(|event| event.author == author && event.sequence > sequence)
            .cloned()
            .collect();
        events.sort_by_key(|event| event.sequence);
        events
    }

    /// All events, ordered by event hash.
    pub fn events(&self) -> impl Iterator<Item = &TaskEvent> {
        self.events.values()
    }
}
