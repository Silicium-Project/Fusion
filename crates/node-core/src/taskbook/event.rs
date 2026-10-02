//! A single signed task event: construction, hashing, verification and the
//! task identifier rule.
//!
//! The signature covers every field except the signature itself (see
//! [`TaskEvent::signing_bytes`]); the event hash covers the whole serialized
//! event, signature included.
//!
//! A task identifier is `<first 32 hex chars of the publisher key>/<name>`:
//! nobody else can propose a task under that identifier (finding another key
//! with the same 128-bit prefix is out of reach), so a task cannot be hijacked
//! by a second, competing proposal.

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};

use super::{
    TaskBookError, TaskEventBody,
    hex::{decode_fixed, hex_encode, sha256_hex},
};

/// Format version written in every event; events with another version are
/// refused.
pub const TASK_BOOK_VERSION: u8 = 2;
/// Hex characters of the publisher key that prefix a task identifier.
pub const TASK_ID_PREFIX_LEN: usize = 32;
/// Longest accepted task name (the part after the prefix).
pub const MAX_TASK_NAME_LEN: usize = 200;

/// Fields every event carries, besides the signature: who, where in the
/// author's chain, when (author clock, informational only) and about which task.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EventHeader {
    pub sequence: u64,
    pub previous_event_hash: String,
    pub issued_at_ms: u64,
    pub task_id: String,
}

/// One signed entry of an author's chain.
///
/// `author` and `signature` are lowercase hex (Ed25519 public key and
/// signature); `previous_event_hash` is empty for the first event
/// (`sequence == 1`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TaskEvent {
    pub version: u8,
    pub author: String,
    pub sequence: u64,
    pub previous_event_hash: String,
    pub issued_at_ms: u64,
    pub task_id: String,
    pub body: TaskEventBody,
    pub signature: String,
}

impl TaskEvent {
    /// Author identifier (hex public key) derived from a signing key.
    pub fn author_id(signing_key: &SigningKey) -> String {
        hex_encode(signing_key.verifying_key().as_bytes())
    }

    /// Task identifier owned by `publisher` (hex key) for a task `name`.
    pub fn task_id_for(publisher: &str, name: &str) -> String {
        let prefix = &publisher[..TASK_ID_PREFIX_LEN.min(publisher.len())];
        format!("{prefix}/{name}")
    }

    /// Builds an event and signs it with `signing_key`.
    pub fn signed(signing_key: &SigningKey, header: EventHeader, body: TaskEventBody) -> Self {
        let mut event = Self {
            version: TASK_BOOK_VERSION,
            author: Self::author_id(signing_key),
            sequence: header.sequence,
            previous_event_hash: header.previous_event_hash,
            issued_at_ms: header.issued_at_ms,
            task_id: header.task_id,
            body,
            signature: String::new(),
        };
        event.signature = hex_encode(&signing_key.sign(&event.signing_bytes()).to_bytes());
        event
    }

    /// Hex SHA-256 of a payload, as stored in a [`super::PayloadRef`].
    pub fn payload_hash(payload: &[u8]) -> String {
        sha256_hex(payload)
    }

    /// Hex SHA-256 of the JSON-serialized event (signature included).
    pub fn event_hash(&self) -> String {
        sha256_hex(&serde_json::to_vec(self).expect("task event is serializable"))
    }

    /// True when `author` owns `task_id` (see the module documentation).
    pub fn owns_task(author: &str, task_id: &str) -> bool {
        author.len() >= TASK_ID_PREFIX_LEN
            && task_id.len() > TASK_ID_PREFIX_LEN + 1
            && task_id.as_bytes()[TASK_ID_PREFIX_LEN] == b'/'
            && task_id[..TASK_ID_PREFIX_LEN] == author[..TASK_ID_PREFIX_LEN]
    }

    /// Checks everything that does not depend on other events: version,
    /// signature, task identifier format and body contents.
    pub fn verify(&self) -> Result<(), TaskBookError> {
        self.verify_signature()?;
        validate_task_id(&self.task_id)?;
        if matches!(self.body, TaskEventBody::TaskProposed { .. })
            && !Self::owns_task(&self.author, &self.task_id)
        {
            return Err(TaskBookError::NotTaskOwner);
        }
        self.body.validate()
    }

    /// Checks the version, the author key and the Ed25519 signature.
    pub fn verify_signature(&self) -> Result<(), TaskBookError> {
        if self.version != TASK_BOOK_VERSION {
            return Err(TaskBookError::VersionMismatch {
                expected: TASK_BOOK_VERSION,
                actual: self.version,
            });
        }
        let public_key = decode_fixed::<32>(&self.author).ok_or(TaskBookError::InvalidAuthor)?;
        let signature =
            decode_fixed::<64>(&self.signature).ok_or(TaskBookError::InvalidSignature)?;
        let verifying_key =
            VerifyingKey::from_bytes(&public_key).map_err(|_| TaskBookError::InvalidAuthor)?;
        verifying_key
            .verify(&self.signing_bytes(), &Signature::from_bytes(&signature))
            .map_err(|_| TaskBookError::InvalidSignature)
    }

    /// Canonical bytes that are signed: every field but `signature`, in a
    /// fixed field order (JSON of a dedicated envelope struct).
    fn signing_bytes(&self) -> Vec<u8> {
        #[derive(Serialize)]
        struct SigningEnvelope<'a> {
            version: u8,
            author: &'a str,
            sequence: u64,
            previous_event_hash: &'a str,
            issued_at_ms: u64,
            task_id: &'a str,
            body: &'a TaskEventBody,
        }

        serde_json::to_vec(&SigningEnvelope {
            version: self.version,
            author: &self.author,
            sequence: self.sequence,
            previous_event_hash: &self.previous_event_hash,
            issued_at_ms: self.issued_at_ms,
            task_id: &self.task_id,
            body: &self.body,
        })
        .expect("task signing envelope is serializable")
    }
}

/// `<32 lowercase hex>/<name>` with a name of 1..=200 characters among
/// `[A-Za-z0-9._:-]`.
fn validate_task_id(task_id: &str) -> Result<(), TaskBookError> {
    let Some((prefix, name)) = task_id.split_once('/') else {
        return Err(TaskBookError::InvalidTaskId);
    };
    let prefix_ok = prefix.len() == TASK_ID_PREFIX_LEN
        && prefix
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte));
    let name_ok = !name.is_empty()
        && name.len() <= MAX_TASK_NAME_LEN
        && name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(&byte));
    if prefix_ok && name_ok {
        Ok(())
    } else {
        Err(TaskBookError::InvalidTaskId)
    }
}
