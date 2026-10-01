//! Deterministic derivation of a task's status from the events of the book.
//!
//! When several events compete (e.g. two claims), the one with the smallest
//! event hash wins, so every peer holding the same events derives the same
//! state whatever the order they were received in.

use serde::{Deserialize, Serialize};

use super::{TaskBook, TaskEvent, TaskEventKind};

/// Status of a task as derived from its events.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DerivedTaskStatus {
    Proposed,
    Claimed,
    Completed,
    Verified,
    Finalized,
    Cancelled,
}

/// Derived state of one task: status, selected claimant and the event that
/// decided the status.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DerivedTaskState {
    pub task_id: String,
    pub status: DerivedTaskStatus,
    pub claimant: Option<String>,
    pub deciding_event_hash: String,
}

impl TaskBook {
    /// Derives the state of `task_id`, or `None` when no event names it.
    ///
    /// A terminal event (finalized / cancelled) wins over everything;
    /// otherwise the most advanced stage present decides (verification >
    /// result > claim > proposal). A task with only `ClaimReleased` events
    /// yields `None`.
    pub fn task_state(&self, task_id: &str) -> Option<DerivedTaskState> {
        let mut candidates: Vec<_> = self
            .events
            .iter()
            .filter(|(_, event)| event.task_id == task_id)
            .map(|(hash, event)| (hash.clone(), event))
            .collect();
        if candidates.is_empty() {
            return None;
        }
        candidates.sort_by(|left, right| left.0.cmp(&right.0));

        let terminal = candidates.iter().filter(|(_, event)| {
            matches!(
                event.kind,
                TaskEventKind::TaskFinalized | TaskEventKind::TaskCancelled
            )
        });
        if let Some((hash, event)) = terminal.min_by(|left, right| left.0.cmp(&right.0)) {
            let status = if event.kind == TaskEventKind::TaskFinalized {
                DerivedTaskStatus::Finalized
            } else {
                DerivedTaskStatus::Cancelled
            };
            return Some(DerivedTaskState {
                task_id: task_id.to_string(),
                status,
                claimant: self.selected_claimant(&candidates),
                deciding_event_hash: hash.clone(),
            });
        }

        let stages = [
            (
                TaskEventKind::VerificationPublished,
                DerivedTaskStatus::Verified,
            ),
            (TaskEventKind::ResultPublished, DerivedTaskStatus::Completed),
            (TaskEventKind::ClaimProposed, DerivedTaskStatus::Claimed),
            (TaskEventKind::TaskProposed, DerivedTaskStatus::Proposed),
        ];
        for (kind, status) in stages {
            if let Some((hash, _)) = candidates.iter().find(|(_, event)| event.kind == kind) {
                return Some(DerivedTaskState {
                    task_id: task_id.to_string(),
                    status,
                    claimant: self.selected_claimant(&candidates),
                    deciding_event_hash: hash.clone(),
                });
            }
        }
        None
    }

    /// Author of the claim with the smallest event hash, if any.
    ///
    /// `ClaimReleased` events are not taken into account.
    fn selected_claimant(&self, candidates: &[(String, &TaskEvent)]) -> Option<String> {
        candidates
            .iter()
            .filter(|(_, event)| event.kind == TaskEventKind::ClaimProposed)
            .map(|(hash, event)| (hash, &event.author))
            .min_by(|left, right| left.0.cmp(right.0))
            .map(|(_, author)| author.clone())
    }
}
