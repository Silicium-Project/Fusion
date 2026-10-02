//! What an event says: the task terms set by the publisher and one variant
//! per lifecycle step ([`TaskEventBody`]).
//!
//! Who may emit each variant is decided when the task state is derived
//! (`state/`), because events of different authors arrive in any order; the
//! checks that need no other event live in [`TaskEventBody::validate`].

use serde::{Deserialize, Serialize};

use super::{TaskBookError, hex::decode_fixed};

/// Longest accepted `payload_ref` (content address of a spec or result).
pub const MAX_PAYLOAD_REF_LEN: usize = 512;
/// Highest number of attempts a publisher may allow for one task.
pub const MAX_ATTEMPTS: u32 = 16;

/// Conditions of a task, signed by its publisher in [`TaskEventBody::TaskProposed`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct TaskTerms {
    /// Lease granted to the accepted claimant, in milliseconds, renewable.
    pub lease_ms: u64,
    /// Lease renewals allowed per attempt (each adds `lease_ms`).
    pub max_renewals: u32,
    /// Attempts allowed before the task is failed (1..=[`MAX_ATTEMPTS`]).
    pub max_attempts: u32,
    /// Independent approvals needed before the result counts as verified.
    pub verifications_required: u32,
    /// Units paid by the publisher to the claimant of the finalized attempt.
    pub reward: u64,
    /// Units paid to each counted verifier of the finalized attempt.
    pub verifier_reward: u64,
}

impl Default for TaskTerms {
    fn default() -> Self {
        Self {
            lease_ms: 120_000,
            max_renewals: 10,
            max_attempts: 3,
            verifications_required: 1,
            reward: 0,
            verifier_reward: 0,
        }
    }
}

/// Reference to content stored elsewhere (task spec or result) and its hash.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PayloadRef {
    /// Content address, e.g. `silicium/task/v1/<id>` or `result://<id>`.
    pub uri: String,
    /// Lowercase hex SHA-256 of the content.
    pub sha256: String,
}

/// Lifecycle step recorded by an event; `attempt` numbers start at 1.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum TaskEventBody {
    /// Publisher: creates the task (spec + terms).
    TaskProposed { spec: PayloadRef, terms: TaskTerms },
    /// Any peer: offers to run `attempt`.
    ClaimProposed { attempt: u32 },
    /// Publisher: picks one claim (by event hash) for `attempt`.
    ClaimAccepted { attempt: u32, claim: String },
    /// Accepted claimant: still working, extends the lease.
    LeaseRenewed { attempt: u32 },
    /// Accepted claimant: gives the attempt up.
    ClaimReleased { attempt: u32 },
    /// Accepted claimant: result of `attempt`.
    ResultPublished { attempt: u32, result: PayloadRef },
    /// Any peer but the claimant: verdict on a result (by event hash).
    VerificationPublished {
        attempt: u32,
        result_event: String,
        approved: bool,
    },
    /// Publisher: accepts the result of `attempt` (triggers settlement).
    TaskFinalized { attempt: u32 },
    /// Publisher: stops the task.
    TaskCancelled,
}

/// Name of a body variant, convenient for logs and filters.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Ord, PartialOrd, Serialize, Deserialize)]
pub enum TaskEventKind {
    TaskProposed,
    ClaimProposed,
    ClaimAccepted,
    LeaseRenewed,
    ClaimReleased,
    ResultPublished,
    VerificationPublished,
    TaskFinalized,
    TaskCancelled,
}

impl TaskEventBody {
    /// Variant name of this body.
    pub fn kind(&self) -> TaskEventKind {
        match self {
            Self::TaskProposed { .. } => TaskEventKind::TaskProposed,
            Self::ClaimProposed { .. } => TaskEventKind::ClaimProposed,
            Self::ClaimAccepted { .. } => TaskEventKind::ClaimAccepted,
            Self::LeaseRenewed { .. } => TaskEventKind::LeaseRenewed,
            Self::ClaimReleased { .. } => TaskEventKind::ClaimReleased,
            Self::ResultPublished { .. } => TaskEventKind::ResultPublished,
            Self::VerificationPublished { .. } => TaskEventKind::VerificationPublished,
            Self::TaskFinalized { .. } => TaskEventKind::TaskFinalized,
            Self::TaskCancelled => TaskEventKind::TaskCancelled,
        }
    }

    /// Attempt number named by the body, if any.
    pub fn attempt(&self) -> Option<u32> {
        match self {
            Self::ClaimProposed { attempt }
            | Self::ClaimAccepted { attempt, .. }
            | Self::LeaseRenewed { attempt }
            | Self::ClaimReleased { attempt }
            | Self::ResultPublished { attempt, .. }
            | Self::VerificationPublished { attempt, .. }
            | Self::TaskFinalized { attempt } => Some(*attempt),
            Self::TaskProposed { .. } | Self::TaskCancelled => None,
        }
    }

    /// Checks that need no other event: hashes, sizes, attempt and terms ranges.
    pub fn validate(&self) -> Result<(), TaskBookError> {
        if let Some(attempt) = self.attempt()
            && !(1..=MAX_ATTEMPTS).contains(&attempt)
        {
            return Err(TaskBookError::InvalidBody("attempt out of range"));
        }
        match self {
            Self::TaskProposed { spec, terms } => {
                validate_payload(spec)?;
                validate_terms(terms)
            }
            Self::ResultPublished { result, .. } => validate_payload(result),
            Self::ClaimAccepted { claim: hash, .. }
            | Self::VerificationPublished {
                result_event: hash, ..
            } => match decode_fixed::<32>(hash) {
                Some(_) => Ok(()),
                None => Err(TaskBookError::InvalidHash),
            },
            _ => Ok(()),
        }
    }
}

fn validate_payload(payload: &PayloadRef) -> Result<(), TaskBookError> {
    if payload.uri.is_empty() || payload.uri.len() > MAX_PAYLOAD_REF_LEN {
        return Err(TaskBookError::InvalidBody("payload reference length"));
    }
    if decode_fixed::<32>(&payload.sha256).is_none() {
        return Err(TaskBookError::InvalidHash);
    }
    Ok(())
}

fn validate_terms(terms: &TaskTerms) -> Result<(), TaskBookError> {
    if terms.lease_ms == 0 {
        return Err(TaskBookError::InvalidBody("lease must be positive"));
    }
    if !(1..=MAX_ATTEMPTS).contains(&terms.max_attempts) {
        return Err(TaskBookError::InvalidBody("max_attempts out of range"));
    }
    if terms.verifications_required > 16 || terms.max_renewals > 10_000 {
        return Err(TaskBookError::InvalidBody("terms out of range"));
    }
    Ok(())
}
