//! Filling gaps in the task book over gossip: when events of an author wait
//! for missing predecessors, ask the topic for them (at most every few
//! seconds per author); answer such requests with the stored events.
//!
//! A node that joins after a task was proposed has no gap to notice: it has
//! never seen the publisher's chain. So when the publisher announces a task
//! again, it also sends that task's history ([`task_history`]); a receiver
//! missing older events of those authors then asks for them as above.

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

/// Stored events of `task_id` (all authors, in book order), bounded: what a
/// node that missed the task needs to derive its state.
pub(crate) fn task_history(taskbook: &TaskBookState, task_id: &str) -> Vec<TaskEvent> {
    taskbook
        .with_book(|book| {
            let mut events: Vec<TaskEvent> = book
                .events()
                .filter(|event| event.task_id == task_id)
                .cloned()
                .collect();
            events.sort_by(|a, b| (&a.author, a.sequence).cmp(&(&b.author, b.sequence)));
            events.truncate(MAX_ANSWER_EVENTS);
            events
        })
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::storage::load_taskbook_state;
    use silicium_node_core::taskbook::{PayloadRef, TaskEventBody, TaskTerms};

    #[test]
    fn the_history_of_a_task_holds_only_its_events_in_chain_order() {
        let dir = std::env::temp_dir().join(format!("silicium-backfill-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let key = libp2p::identity::Keypair::generate_ed25519();
        let taskbook = load_taskbook_state(&dir, &key).unwrap();
        let propose = |name: &str| {
            let task_id = taskbook.owned_task_id(name);
            let spec = PayloadRef {
                uri: format!("silicium/task/v1/{task_id}"),
                sha256: TaskEvent::payload_hash(name.as_bytes()),
            };
            let body = TaskEventBody::TaskProposed {
                spec,
                terms: TaskTerms::default(),
            };
            taskbook.append_signed(&task_id, body).unwrap();
            task_id
        };
        let first = propose("first");
        propose("second");
        taskbook
            .append_signed(&first, TaskEventBody::ClaimProposed { attempt: 1 })
            .unwrap();

        let history = task_history(&taskbook, &first);
        assert_eq!(history.len(), 2);
        assert!(history.iter().all(|event| event.task_id == first));
        assert!(history[0].sequence < history[1].sequence);
        std::fs::remove_dir_all(&dir).ok();
    }
}
