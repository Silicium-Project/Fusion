//! Errors returned when validating, appending, persisting or loading task
//! events.

use thiserror::Error;

/// Reason why a task event was refused or could not be stored.
#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum TaskBookError {
    #[error("task event version mismatch: expected {expected}, got {actual}")]
    VersionMismatch { expected: u8, actual: u8 },
    #[error("invalid author public key")]
    InvalidAuthor,
    #[error("invalid event signature")]
    InvalidSignature,
    #[error("invalid event hash or payload hash")]
    InvalidHash,
    #[error("event sequence must start at one")]
    InvalidInitialSequence,
    #[error("event sequence gap for author {author}: expected {expected}, got {actual}")]
    SequenceGap {
        author: String,
        expected: u64,
        actual: u64,
    },
    #[error("event predecessor does not match the current author head")]
    PreviousEventMismatch,
    #[error("event conflicts with an existing author chain")]
    ConflictingEvent,
    #[error("payload hash mismatch")]
    PayloadHashMismatch,
    #[error("event serialization failed: {0}")]
    Serialization(String),
    #[error("event persistence failed: {0}")]
    Io(String),
}
