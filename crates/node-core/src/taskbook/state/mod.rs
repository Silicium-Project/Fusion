//! Deterministic derivation of a task's state from the events of the book.
//!
//! Every peer holding the same events derives the same state whatever order
//! they arrived in, because the decisions follow the publisher's own chain
//! (totally ordered by sequence) and never a race between authors:
//!
//! - only the publisher accepts a claim, finalizes or cancels (`roles.rs`);
//! - only the accepted claimant renews its lease, releases or publishes the
//!   result; a verifier may not verify its own result (`attempts.rs`);
//! - the only clock-dependent input is `now_ms`, used to tell whether the
//!   lease of the running attempt has expired (lease start = the publisher's
//!   acceptance time, length = terms, extended by the claimant's renewals).
//!
//! Events of authors caught equivocating are ignored.

mod attempts;
mod claims;
mod roles;

use serde::{Deserialize, Serialize};

use super::{PayloadRef, TaskBook, TaskTerms};

/// Status of a task as derived from its events.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DerivedTaskStatus {
    /// Proposed, no claim accepted yet: claims for attempt 1 are welcome.
    Open,
    /// An attempt runs under a valid lease.
    Claimed,
    /// The claimant stopped renewing its lease in time.
    LeaseExpired,
    /// The claimant gave the attempt up.
    Released,
    /// A result is published, not yet verified enough.
    Completed,
    /// The result has the required approvals.
    Verified,
    /// A verifier rejected the result.
    Rejected,
    /// The last allowed attempt failed.
    Failed,
    /// The publisher accepted a result (terminal).
    Finalized,
    /// The publisher stopped the task (terminal).
    Cancelled,
}

impl DerivedTaskStatus {
    /// Attempt ended without a usable result.
    pub fn is_failed_attempt(self) -> bool {
        matches!(self, Self::LeaseExpired | Self::Released | Self::Rejected)
    }

    /// No further event can change the task.
    pub fn is_terminal(self) -> bool {
        matches!(self, Self::Finalized | Self::Cancelled | Self::Failed)
    }
}

/// Result of an attempt and the verdicts it received.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ResultState {
    pub event_hash: String,
    pub result: PayloadRef,
    /// Approving verifiers as `(verification event hash, author)`, by hash.
    pub approvals: Vec<(String, String)>,
    /// Rejecting verifiers as `(verification event hash, author)`, by hash.
    pub rejections: Vec<(String, String)>,
}

/// One accepted attempt.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttemptState {
    pub attempt: u32,
    pub claimant: String,
    pub claim_event: String,
    pub accepted_at_ms: u64,
    pub renewals: u32,
    pub lease_expires_at_ms: u64,
    pub released: bool,
    pub result: Option<ResultState>,
}

/// Derived state of one task.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DerivedTaskState {
    pub task_id: String,
    pub publisher: String,
    pub proposal_event: String,
    pub spec: PayloadRef,
    pub terms: TaskTerms,
    pub status: DerivedTaskStatus,
    /// Accepted attempts, oldest first.
    pub attempts: Vec<AttemptState>,
    /// Attempt that claims are now welcome for, if any.
    pub next_attempt: Option<u32>,
    /// Attempt whose result the publisher accepted.
    pub finalized_attempt: Option<u32>,
}

impl DerivedTaskState {
    /// Claimant of the latest attempt, if any.
    pub fn claimant(&self) -> Option<&str> {
        self.attempts
            .last()
            .map(|attempt| attempt.claimant.as_str())
    }
}

impl TaskBook {
    /// Derives the state of `task_id` at time `now_ms` (Unix milliseconds),
    /// or `None` when the book holds no valid proposal for it.
    pub fn task_state(&self, task_id: &str, now_ms: u64) -> Option<DerivedTaskState> {
        let view = roles::TaskView::new(self, task_id)?;
        let outcome = view.replay_publisher_decisions();
        Some(attempts::summarize(&view, outcome, now_ms))
    }
}

pub use claims::OpenClaim;
