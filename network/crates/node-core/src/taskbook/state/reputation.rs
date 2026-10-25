//! Reputation derived from the book: for every author, the attempts it
//! carried to finalization and the attempts it let fail (lease lapsed,
//! released, rejected, or replaced by a newer attempt). Every peer derives
//! the same figures from the same events.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use super::super::{TaskBook, TaskEventBody};

/// Track record of one author as a claimant.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct AuthorRecord {
    pub completed: u32,
    pub failed: u32,
}

impl AuthorRecord {
    /// Posterior mean of a Beta(1, 1) prior: 0.5 for a newcomer, towards 1
    /// with finalized attempts, towards 0 with failed ones.
    pub fn score(&self) -> f64 {
        (f64::from(self.completed) + 1.0) / (f64::from(self.completed + self.failed) + 2.0)
    }
}

impl TaskBook {
    /// Track record of every author that held an attempt, at `now_ms`.
    pub fn author_records(&self, now_ms: u64) -> BTreeMap<String, AuthorRecord> {
        let mut task_ids: Vec<&str> = self
            .events
            .values()
            .filter(|event| matches!(event.body, TaskEventBody::TaskProposed { .. }))
            .map(|event| event.task_id.as_str())
            .collect();
        task_ids.sort_unstable();
        task_ids.dedup();
        let mut records: BTreeMap<String, AuthorRecord> = BTreeMap::new();
        for task_id in task_ids {
            let Some(state) = self.task_state(task_id, now_ms) else {
                continue;
            };
            let last = state.attempts.len();
            for (position, attempt) in state.attempts.iter().enumerate() {
                let record = records.entry(attempt.claimant.clone()).or_default();
                if state.finalized_attempt == Some(attempt.attempt) {
                    record.completed += 1;
                } else if position + 1 < last
                    || state.status.is_failed_attempt()
                    || state.status == super::DerivedTaskStatus::Failed
                {
                    record.failed += 1;
                }
            }
        }
        records
    }
}
