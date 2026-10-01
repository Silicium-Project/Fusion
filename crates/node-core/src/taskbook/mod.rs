//! Append-only task event log.
//!
//! Every event is signed with the author's Ed25519 key and chained to the
//! author's previous event (sequence number + previous hash), so gaps and forks
//! are detected when merging logs received from other peers.
//!
//! Layout:
//! - `event`: [`TaskEvent`] (signing, hashing, verification) and its kind.
//! - `book`: [`TaskBook`] chain validation, merge and accessors.
//! - `persistence`: JSON Lines load / append of a [`TaskBook`].
//! - `state`: [`DerivedTaskState`] derivation from the events of a task.
//! - `error`: [`TaskBookError`].
//! - `hex`: local hex / SHA-256 helpers.

mod book;
mod error;
mod event;
mod hex;
mod persistence;
mod state;

pub use book::TaskBook;
pub use error::TaskBookError;
pub use event::{TASK_BOOK_VERSION, TaskEvent, TaskEventKind};
pub use state::{DerivedTaskState, DerivedTaskStatus};

#[cfg(test)]
mod tests;
