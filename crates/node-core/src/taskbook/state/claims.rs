//! Claims waiting for the publisher's decision. The book never picks a
//! winner by itself (a winner chosen by hash could be ground by trying many
//! variants); the publisher chooses among these and signs a `ClaimAccepted`.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use super::super::{TaskBook, TaskEventBody};

/// A claim for the attempt that is currently open.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OpenClaim {
    pub event_hash: String,
    pub author: String,
    pub issued_at_ms: u64,
}

impl TaskBook {
    /// Claims for the open attempt of `task_id` at `now_ms`: one per author
    /// (its earliest), excluding the claimants of earlier attempts, ordered
    /// by event hash. Empty when no attempt is open.
    pub fn open_claims(&self, task_id: &str, now_ms: u64) -> Vec<OpenClaim> {
        let Some(state) = self.task_state(task_id, now_ms) else {
            return Vec::new();
        };
        let Some(next_attempt) = state.next_attempt else {
            return Vec::new();
        };
        let previous: Vec<&str> = state.attempts.iter().map(|a| a.claimant.as_str()).collect();
        let mut by_author: BTreeMap<&str, (&str, u64, u64)> = BTreeMap::new();
        for (hash, event) in self.task_events(task_id) {
            let wanted = event.body
                == (TaskEventBody::ClaimProposed {
                    attempt: next_attempt,
                })
                && !previous.contains(&event.author.as_str())
                && !self.equivocators.contains(&event.author);
            if !wanted {
                continue;
            }
            let entry = by_author.entry(&event.author).or_insert((
                hash,
                event.sequence,
                event.issued_at_ms,
            ));
            if event.sequence < entry.1 {
                *entry = (hash, event.sequence, event.issued_at_ms);
            }
        }
        let mut claims: Vec<OpenClaim> = by_author
            .into_iter()
            .map(|(author, (hash, _, issued_at_ms))| OpenClaim {
                event_hash: hash.to_string(),
                author: author.to_string(),
                issued_at_ms,
            })
            .collect();
        claims.sort_by(|left, right| left.event_hash.cmp(&right.event_hash));
        claims
    }
}
