use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::Path,
};
use thiserror::Error;

pub const TASK_BOOK_VERSION: u8 = 1;

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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DerivedTaskStatus {
    Proposed,
    Claimed,
    Completed,
    Verified,
    Finalized,
    Cancelled,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DerivedTaskState {
    pub task_id: String,
    pub status: DerivedTaskStatus,
    pub claimant: Option<String>,
    pub deciding_event_hash: String,
}

#[derive(Debug, Clone, Default)]
pub struct TaskBook {
    events: BTreeMap<String, TaskEvent>,
    heads: BTreeMap<String, String>,
}

impl TaskEvent {
    pub fn author_id(signing_key: &SigningKey) -> String {
        hex_encode(signing_key.verifying_key().as_bytes())
    }

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

    pub fn payload_hash(payload: &[u8]) -> String {
        sha256_hex(payload)
    }

    pub fn event_hash(&self) -> String {
        sha256_hex(&serde_json::to_vec(self).expect("task event is serializable"))
    }

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

    pub fn verify_payload(&self, payload: &[u8]) -> Result<(), TaskBookError> {
        if Self::payload_hash(payload) == self.payload_hash {
            Ok(())
        } else {
            Err(TaskBookError::PayloadHashMismatch)
        }
    }

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

impl TaskBook {
    pub fn append(&mut self, event: TaskEvent) -> Result<String, TaskBookError> {
        event.verify_signature()?;
        if decode_fixed::<32>(&event.payload_hash).is_none() {
            return Err(TaskBookError::InvalidHash);
        }

        let event_hash = event.event_hash();
        if let Some(existing) = self.events.get(&event_hash) {
            if existing == &event {
                return Ok(event_hash);
            }
            return Err(TaskBookError::ConflictingEvent);
        }

        let current_head = self.heads.get(&event.author);
        match (event.sequence, current_head) {
            (1, None) if event.previous_event_hash.is_empty() => {}
            (1, Some(_)) => return Err(TaskBookError::ConflictingEvent),
            (1, None) => return Err(TaskBookError::InvalidInitialSequence),
            (sequence, Some(head_hash)) => {
                let head = self
                    .events
                    .get(head_hash)
                    .ok_or(TaskBookError::PreviousEventMismatch)?;
                if sequence != head.sequence + 1 {
                    return Err(TaskBookError::SequenceGap {
                        author: event.author.clone(),
                        expected: head.sequence + 1,
                        actual: sequence,
                    });
                }
                if event.previous_event_hash != *head_hash {
                    return Err(TaskBookError::PreviousEventMismatch);
                }
            }
            (sequence, None) => {
                return Err(TaskBookError::SequenceGap {
                    author: event.author.clone(),
                    expected: 1,
                    actual: sequence,
                });
            }
        }

        self.events.insert(event_hash.clone(), event.clone());
        self.heads.insert(event.author, event_hash.clone());
        Ok(event_hash)
    }

    pub fn append_persisted(
        &mut self,
        path: impl AsRef<Path>,
        event: TaskEvent,
    ) -> Result<String, TaskBookError> {
        let event_hash = event.event_hash();
        if let Some(existing) = self.events.get(&event_hash)
            && existing == &event
        {
            return Ok(event_hash);
        }
        let mut next = self.clone();
        let event_hash = next.append(event.clone())?;
        let path = path.as_ref();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|err| TaskBookError::Io(err.to_string()))?;
        }
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .map_err(|err| TaskBookError::Io(err.to_string()))?;
        serde_json::to_writer(&mut file, &event)
            .map_err(|err| TaskBookError::Serialization(err.to_string()))?;
        file.write_all(b"\n")
            .map_err(|err| TaskBookError::Io(err.to_string()))?;
        *self = next;
        Ok(event_hash)
    }

    pub fn load(path: impl AsRef<Path>) -> Result<Self, TaskBookError> {
        let path = path.as_ref();
        if !path.exists() {
            return Ok(Self::default());
        }
        let file = fs::File::open(path).map_err(|err| TaskBookError::Io(err.to_string()))?;
        let mut book = Self::default();
        for line in BufReader::new(file).lines() {
            let line = line.map_err(|err| TaskBookError::Io(err.to_string()))?;
            if line.trim().is_empty() {
                continue;
            }
            let event: TaskEvent = serde_json::from_str(&line)
                .map_err(|err| TaskBookError::Serialization(err.to_string()))?;
            book.append(event)?;
        }
        Ok(book)
    }

    pub fn merge(
        &mut self,
        events: impl IntoIterator<Item = TaskEvent>,
    ) -> Result<usize, TaskBookError> {
        let mut events: Vec<_> = events.into_iter().collect();
        events.sort_by_key(|event| (event.author.clone(), event.sequence, event.event_hash()));
        let before = self.events.len();
        for event in events {
            self.append(event)?;
        }
        Ok(self.events.len() - before)
    }

    pub fn head(&self, author: &str) -> Option<&str> {
        self.heads.get(author).map(String::as_str)
    }

    pub fn next_sequence(&self, author: &str) -> u64 {
        self.heads
            .get(author)
            .and_then(|hash| self.events.get(hash))
            .map(|event| event.sequence + 1)
            .unwrap_or(1)
    }

    pub fn heads(&self) -> BTreeMap<String, String> {
        self.heads.clone()
    }

    pub fn events_for_author_after(&self, author: &str, sequence: u64) -> Vec<TaskEvent> {
        let mut events: Vec<_> = self
            .events
            .values()
            .filter(|event| event.author == author && event.sequence > sequence)
            .cloned()
            .collect();
        events.sort_by_key(|event| event.sequence);
        events
    }

    pub fn events(&self) -> impl Iterator<Item = &TaskEvent> {
        self.events.values()
    }

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

    fn selected_claimant(&self, candidates: &[(String, &TaskEvent)]) -> Option<String> {
        candidates
            .iter()
            .filter(|(_, event)| event.kind == TaskEventKind::ClaimProposed)
            .map(|(hash, event)| (hash, &event.author))
            .min_by(|left, right| left.0.cmp(right.0))
            .map(|(_, author)| author.clone())
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    hex_encode(&digest)
}

fn hex_encode(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

fn decode_fixed<const N: usize>(value: &str) -> Option<[u8; N]> {
    if value.len() != N * 2 {
        return None;
    }
    let bytes = value.as_bytes();
    let mut output = [0u8; N];
    for index in 0..N {
        output[index] = (hex_digit(bytes[index * 2])? << 4) | hex_digit(bytes[index * 2 + 1])?;
    }
    Some(output)
}

fn hex_digit(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        time::{SystemTime, UNIX_EPOCH},
    };

    fn key(seed: u8) -> SigningKey {
        SigningKey::from_bytes(&[seed; 32])
    }

    fn proposal(signing_key: &SigningKey, sequence: u64, previous: &str, task: &str) -> TaskEvent {
        let payload = format!("manifest:{task}");
        TaskEvent::signed(
            signing_key,
            sequence,
            previous,
            TaskEventKind::TaskProposed,
            task,
            format!("cas://{task}"),
            TaskEvent::payload_hash(payload.as_bytes()),
        )
    }

    #[test]
    fn signed_event_roundtrips_and_verifies_payload() {
        let signing_key = key(7);
        let event = proposal(&signing_key, 1, "", "task-a");
        event.verify_signature().unwrap();
        event.verify_payload(b"manifest:task-a").unwrap();
        assert_eq!(event.author.len(), 64);
        assert_eq!(event.event_hash().len(), 64);
    }

    #[test]
    fn invalid_signature_and_payload_are_rejected() {
        let signing_key = key(8);
        let mut event = proposal(&signing_key, 1, "", "task-a");
        event.signature.replace_range(..2, "00");
        assert!(matches!(
            event.verify_signature(),
            Err(TaskBookError::InvalidSignature)
        ));

        let event = proposal(&signing_key, 1, "", "task-a");
        assert!(matches!(
            event.verify_payload(b"tampered"),
            Err(TaskBookError::PayloadHashMismatch)
        ));
    }

    #[test]
    fn sequence_gaps_and_forks_are_rejected() {
        let signing_key = key(9);
        let first = proposal(&signing_key, 1, "", "task-a");
        let mut book = TaskBook::default();
        let first_hash = book.append(first).unwrap();

        let gap = proposal(&signing_key, 3, &first_hash, "task-a");
        assert!(matches!(
            book.append(gap),
            Err(TaskBookError::SequenceGap { .. })
        ));

        let fork = proposal(&signing_key, 2, "wrong", "task-a");
        assert!(matches!(
            book.append(fork),
            Err(TaskBookError::PreviousEventMismatch)
        ));
    }

    #[test]
    fn persistence_replays_the_same_heads_and_state() {
        let root = std::env::temp_dir().join(format!(
            "silicium-taskbook-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let path = root.join("events.jsonl");
        let signing_key = key(10);
        let mut book = TaskBook::default();
        let event = proposal(&signing_key, 1, "", "task-a");
        book.append_persisted(&path, event).unwrap();
        let duplicate = book.events().next().cloned().unwrap();
        book.append_persisted(&path, duplicate).unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap().lines().count(), 1);

        let restored = TaskBook::load(&path).unwrap();
        assert_eq!(restored.heads(), book.heads());
        assert_eq!(restored.task_state("task-a"), book.task_state("task-a"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn merge_selects_conflicting_claims_deterministically() {
        let proposer = key(11);
        let worker_a = key(12);
        let worker_b = key(13);
        let proposal = proposal(&proposer, 1, "", "task-a");
        let proposal_hash = proposal.event_hash();
        let claim_a = TaskEvent::signed(
            &worker_a,
            1,
            "",
            TaskEventKind::ClaimProposed,
            "task-a",
            "cas://claim-a",
            TaskEvent::payload_hash(b"a"),
        );
        let claim_b = TaskEvent::signed(
            &worker_b,
            1,
            "",
            TaskEventKind::ClaimProposed,
            "task-a",
            "cas://claim-b",
            TaskEvent::payload_hash(b"b"),
        );
        let mut left = TaskBook::default();
        left.append(proposal.clone()).unwrap();
        left.merge([claim_b.clone(), claim_a.clone()]).unwrap();

        let mut right = TaskBook::default();
        right.append(proposal).unwrap();
        right.merge([claim_a.clone(), claim_b]).unwrap();

        assert_eq!(left.task_state("task-a"), right.task_state("task-a"));
        assert_eq!(
            left.head(&hex_encode(worker_a.verifying_key().as_bytes())),
            Some(claim_a.event_hash().as_str())
        );
        assert_eq!(proposal_hash.len(), 64);
    }
}
