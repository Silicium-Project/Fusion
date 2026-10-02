//! Signed, replicated log of task events (the "task book").
//!
//! Every event is signed with its author's Ed25519 key and chained to the
//! author's previous event (sequence number + previous hash). Each peer keeps
//! a copy, merges what others send, and derives the same task states.
//!
//! Rules that make the book safe to share with untrusted peers:
//! - a task identifier starts with its publisher's key, so nobody else can
//!   propose it; only the publisher accepts a claim, finalizes or cancels;
//! - claims are offers: the publisher picks one (no race won by hash);
//! - only the accepted claimant renews its lease, releases or publishes the
//!   result; only verifiers accepted by the publisher give verdicts that
//!   count (never the claimant), on milestones drawn after the result;
//! - an attempt whose lease lapses, is released or rejected can be retried,
//!   up to the publisher's `max_attempts`;
//! - events arriving out of order wait for their predecessors; an author
//!   signing two versions of an event is ignored; per-author limits bound
//!   the memory and disk a peer can use.
//!
//! Layout:
//! - `body`: [`TaskEventBody`] variants and [`TaskTerms`];
//! - `event`: [`TaskEvent`] signing, hashing, verification, task identifiers;
//! - `book`: [`TaskBook`] chain validation, equivocation, limits, accessors;
//! - `backfill`: out-of-order reception and gap reporting;
//! - `persistence`: JSON Lines load / append;
//! - `state/`: task state derivation (roles, attempts, open claims);
//! - `settlement`: payments due for finalized tasks;
//! - `error`: [`TaskBookError`]; `hex`: hex / SHA-256 helpers.

mod backfill;
mod body;
mod book;
mod error;
mod event;
mod hex;
mod persistence;
mod settlement;
mod state;

pub use backfill::{MAX_PENDING_PER_AUTHOR, MAX_PENDING_TOTAL, MissingEvents, Received};
pub use body::{
    MAX_ATTEMPTS, MAX_MILESTONES, MAX_PAYLOAD_REF_LEN, MilestoneSample, PayloadRef, TaskEventBody,
    TaskEventKind, TaskTerms,
};
pub use book::{MAX_EVENTS_PER_AUTHOR_PER_TASK, TaskBook};
pub use error::TaskBookError;
pub use event::{EventHeader, MAX_TASK_NAME_LEN, TASK_BOOK_VERSION, TASK_ID_PREFIX_LEN, TaskEvent};
pub use persistence::LoadReport;
pub use settlement::{Settlement, SettlementRole};
pub use state::{
    AttemptState, AuthorRecord, DerivedTaskState, DerivedTaskStatus, OpenClaim, OpenVerification,
    ResultState, VerifierState, milestones_cover_region, sample_milestones,
    verification_sample_count,
};

#[cfg(test)]
mod tests;
