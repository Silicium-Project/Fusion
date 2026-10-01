//! A single signed task event: construction, hashing and verification.
//!
//! The signature covers every field except the signature itself (see
//! [`TaskEvent::signing_bytes`]); the event hash covers the whole serialized
//! event, signature included.

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};

use super::{
    TaskBookError,
    hex::{decode_fixed, hex_encode, sha256_hex},
};

/// Format version written in every event; events with another version are
/// refused.
pub const TASK_BOOK_VERSION: u8 = 1;

/// Lifecycle step recorded by an event.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Ord, PartialOrd, Serialize, Deserialize)]
pub enum TaskEventKind {
    TaskProposed,
    ClaimProposed,
    ClaimReleased,
    ResultPublished,
    VerificationPublished,
    TaskFinalized,
    TaskCancelled,
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
    pub kind: TaskEventKind,
    pub task_id: String,
    pub payload_ref: String,
    pub payload_hash: String,
    pub signature: String,
}

impl TaskEvent {
    /// Author identifier (hex public key) derived from a signing key.
    pub fn author_id(signing_key: &SigningKey) -> String {
        hex_encode(signing_key.verifying_key().as_bytes())
    }

    /// Builds an event and signs it with `signing_key`.
    pub fn signed(
        signing_key: &SigningKey,
        sequence: u64,
        previous_event_hash: impl Into<String>,
        kind: TaskEventKind,
        task_id: impl Into<String>,
        payload_ref: impl Into<String>,
        payload_hash: impl Into<String>,
    ) -> Self {
        let mut event = Self {
            version: TASK_BOOK_VERSION,
            author: Self::author_id(signing_key),
            sequence,
            previous_event_hash: previous_event_hash.into(),
            kind,
            task_id: task_id.into(),
            payload_ref: payload_ref.into(),
            payload_hash: payload_hash.into(),
            signature: String::new(),
        };
        event.signature = hex_encode(&signing_key.sign(&event.signing_bytes()).to_bytes());
        event
    }

    /// Hex SHA-256 of a payload, as stored in `payload_hash`.
    pub fn payload_hash(payload: &[u8]) -> String {
        sha256_hex(payload)
    }

    /// Hex SHA-256 of the JSON-serialized event (signature included).
    pub fn event_hash(&self) -> String {
        sha256_hex(&serde_json::to_vec(self).expect("task event is serializable"))
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

    /// Checks that `payload` hashes to `payload_hash`.
    pub fn verify_payload(&self, payload: &[u8]) -> Result<(), TaskBookError> {
        if Self::payload_hash(payload) == self.payload_hash {
            Ok(())
        } else {
            Err(TaskBookError::PayloadHashMismatch)
        }
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
            kind: TaskEventKind,
            task_id: &'a str,
            payload_ref: &'a str,
            payload_hash: &'a str,
        }

        serde_json::to_vec(&SigningEnvelope {
            version: self.version,
            author: &self.author,
            sequence: self.sequence,
            previous_event_hash: &self.previous_event_hash,
            kind: self.kind,
            task_id: &self.task_id,
            payload_ref: &self.payload_ref,
            payload_hash: &self.payload_hash,
        })
        .expect("task signing envelope is serializable")
    }
}
