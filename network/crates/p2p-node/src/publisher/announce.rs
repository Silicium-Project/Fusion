//! Spacing of task re-announcements.
//!
//! A task is gossiped once when it is published. A worker that was not in
//! the gossip mesh at that moment (it joined later, or its connection was
//! being set up) never receives it, even though it catches up on the task
//! book events. So the publisher announces a task again while nobody claims
//! it (or nobody offers to verify its result), every [`REANNOUNCE_MS`].

use std::collections::BTreeMap;

/// Delay between two announcements of the same task.
pub(crate) const REANNOUNCE_MS: u64 = 10_000;

/// Last announcement time of each task waiting for a worker or a verifier.
#[derive(Debug, Default)]
pub(crate) struct Reannouncer {
    last: BTreeMap<String, u64>,
}

impl Reannouncer {
    /// True when `task_id` should be announced again at `now`. The first
    /// call only starts the clock: the task was just gossiped on publication.
    pub(crate) fn due(&mut self, task_id: &str, now: u64) -> bool {
        match self.last.get_mut(task_id) {
            None => {
                self.last.insert(task_id.to_string(), now);
                false
            }
            Some(last) if now.saturating_sub(*last) >= REANNOUNCE_MS => {
                *last = now;
                true
            }
            Some(_) => false,
        }
    }

    /// Stops tracking a finished task.
    pub(crate) fn forget(&mut self, task_id: &str) {
        self.last.remove(task_id);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_task_is_announced_again_every_interval() {
        let mut announcer = Reannouncer::default();
        assert!(!announcer.due("t", 0), "just published");
        assert!(!announcer.due("t", REANNOUNCE_MS - 1));
        assert!(announcer.due("t", REANNOUNCE_MS));
        assert!(!announcer.due("t", REANNOUNCE_MS + 1));
        assert!(announcer.due("t", 2 * REANNOUNCE_MS));
        announcer.forget("t");
        assert!(!announcer.due("t", 3 * REANNOUNCE_MS), "clock restarted");
    }
}
