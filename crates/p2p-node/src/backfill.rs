//! Filling gaps in the task book over gossip: when events of an author wait
//! for missing predecessors, ask the topic for them (at most every few
//! seconds per author); answer such requests with the stored events.

use crate::storage::TaskBookState;
use silicium_node_core::taskbook::TaskEvent;
use std::{
    collections::BTreeMap,
    time::{Duration, Instant},
};

/// Minimum delay between two requests for the same author.
const REQUEST_INTERVAL: Duration = Duration::from_secs(3);
/// Most events sent in answer to one request.
const MAX_ANSWER_EVENTS: usize = 64;

/// `(author, after_sequence)` pairs to request now.
pub(crate) fn requests_for_gaps(
    taskbook: &TaskBookState,
    last_requested: &mut BTreeMap<String, Instant>,
) -> Vec<(String, u64)> {
    let gaps = taskbook
        .with_book(|book| book.missing_events())
        .unwrap_or_default();
    let now = Instant::now();
    gaps.into_iter()
        .filter(|gap| {
            let recent = last_requested
                .get(&gap.author)
                .is_some_and(|at| now.duration_since(*at) < REQUEST_INTERVAL);
            if !recent {
                last_requested.insert(gap.author.clone(), now);
            }
            !recent
        })
        .map(|gap| (gap.author, gap.after_sequence))
        .collect()
}

/// Stored events of `author` after `after_sequence`, bounded.
pub(crate) fn answer(
    taskbook: &TaskBookState,
    author: &str,
    after_sequence: u64,
) -> Vec<TaskEvent> {
    taskbook
        .with_book(|book| {
            let mut events = book.events_for_author_after(author, after_sequence);
            events.truncate(MAX_ANSWER_EVENTS);
            events
        })
        .unwrap_or_default()
}
