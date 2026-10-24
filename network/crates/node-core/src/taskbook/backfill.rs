//! Events received out of order (from gossip or a peer): they wait in a
//! bounded buffer until their predecessors arrive, and the book reports which
//! ranges to ask peers for, instead of rejecting the author for good.

use super::{TaskBook, TaskBookError, TaskEvent, book::Check};

/// Most events kept waiting for one author.
pub const MAX_PENDING_PER_AUTHOR: usize = 256;
/// Most events kept waiting in total.
pub const MAX_PENDING_TOTAL: usize = 16_384;

/// Outcome of [`TaskBook::receive`].
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Received {
    /// Hashes of the events added to the book, in insertion order (the
    /// received event and any waiting successors it unblocked).
    pub accepted: Vec<String>,
    /// True when the event waits for a missing predecessor.
    pub pending: bool,
}

/// A gap to fill: ask a peer for the events of `author` after
/// `after_sequence` (see [`TaskBook::events_for_author_after`]).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MissingEvents {
    pub author: String,
    pub after_sequence: u64,
    /// Sequence of the first event already waiting (exclusive end of the gap).
    pub first_waiting: u64,
}

impl TaskBook {
    /// Takes an event in any order: adds it when it is next in its author's
    /// chain (then every waiting successor), buffers it when a predecessor is
    /// missing, and refuses invalid or conflicting events.
    pub fn receive(&mut self, event: TaskEvent) -> Result<Received, TaskBookError> {
        let mut accepted = Vec::new();
        let pending = self.receive_with(event, |_, hash| {
            accepted.push(hash.to_string());
            Ok(())
        })?;
        Ok(Received { accepted, pending })
    }

    /// Core of [`TaskBook::receive`]; `on_accept` runs before each insertion
    /// (persistence writes the event there) and can abort it.
    pub(super) fn receive_with(
        &mut self,
        event: TaskEvent,
        mut on_accept: impl FnMut(&TaskEvent, &str) -> Result<(), TaskBookError>,
    ) -> Result<bool, TaskBookError> {
        event.verify()?;
        let author = event.author.clone();
        if event.sequence > self.next_sequence(&author) {
            self.buffer(event)?;
            return Ok(true);
        }
        let hash = event.event_hash();
        if self.check(&event, &hash)? == Check::Duplicate {
            return Ok(false);
        }
        on_accept(&event, &hash)?;
        self.insert(event, hash);
        self.drain(&author, &mut on_accept)?;
        Ok(false)
    }

    /// Receives a batch of events (e.g. a peer's answer to a backfill
    /// request); returns how many were added. Events are sorted by author
    /// and sequence first, so the arrival order does not matter. Invalid
    /// events are skipped; the first error is returned after the whole batch
    /// has been processed.
    pub fn merge(
        &mut self,
        events: impl IntoIterator<Item = TaskEvent>,
    ) -> Result<usize, TaskBookError> {
        let mut events: Vec<_> = events.into_iter().collect();
        events.sort_by(|left, right| {
            (&left.author, left.sequence).cmp(&(&right.author, right.sequence))
        });
        let mut added = 0;
        let mut first_error = None;
        for event in events {
            match self.receive(event) {
                Ok(received) => added += received.accepted.len(),
                Err(error) => {
                    first_error.get_or_insert(error);
                }
            }
        }
        match first_error {
            Some(error) if added == 0 => Err(error),
            _ => Ok(added),
        }
    }

    /// Ranges to request from peers, one per author with waiting events.
    pub fn missing_events(&self) -> Vec<MissingEvents> {
        self.pending
            .iter()
            .filter_map(|(author, waiting)| {
                let first_waiting = *waiting.keys().next()?;
                Some(MissingEvents {
                    author: author.clone(),
                    after_sequence: self.next_sequence(author) - 1,
                    first_waiting,
                })
            })
            .collect()
    }

    /// Number of events waiting for a predecessor.
    pub fn pending_count(&self) -> usize {
        self.pending.values().map(|waiting| waiting.len()).sum()
    }

    fn buffer(&mut self, event: TaskEvent) -> Result<(), TaskBookError> {
        if self.equivocators.contains(&event.author) {
            return Err(TaskBookError::Equivocation(event.author));
        }
        let total = self.pending_count();
        let waiting = self.pending.entry(event.author.clone()).or_default();
        if let Some(existing) = waiting.get(&event.sequence) {
            if *existing == event {
                return Ok(());
            }
            let author = event.author.clone();
            self.pending.remove(&author);
            self.equivocators.insert(author.clone());
            return Err(TaskBookError::Equivocation(author));
        }
        if waiting.len() >= MAX_PENDING_PER_AUTHOR || total >= MAX_PENDING_TOTAL {
            return Err(TaskBookError::PendingFull);
        }
        waiting.insert(event.sequence, event);
        Ok(())
    }

    /// Inserts the waiting events of `author` that now follow its head.
    fn drain(
        &mut self,
        author: &str,
        on_accept: &mut impl FnMut(&TaskEvent, &str) -> Result<(), TaskBookError>,
    ) -> Result<(), TaskBookError> {
        let head_sequence = self.next_sequence(author) - 1;
        if let Some(waiting) = self.pending.get_mut(author) {
            // Events that reached the book another way are no longer waiting.
            waiting.retain(|sequence, _| *sequence > head_sequence);
        }
        loop {
            let next = self.next_sequence(author);
            let Some(event) = self
                .pending
                .get_mut(author)
                .and_then(|waiting| waiting.remove(&next))
            else {
                break;
            };
            let hash = event.event_hash();
            match self.check(&event, &hash) {
                Ok(Check::Next) => {
                    on_accept(&event, &hash)?;
                    self.insert(event, hash);
                }
                Ok(Check::Duplicate) => {}
                // A waiting event that does not link to the real predecessor
                // is dropped; the rest of the buffer cannot follow it either.
                Err(_) => {
                    self.pending.remove(author);
                    break;
                }
            }
        }
        if self
            .pending
            .get(author)
            .is_some_and(|waiting| waiting.is_empty())
        {
            self.pending.remove(author);
        }
        Ok(())
    }
}
