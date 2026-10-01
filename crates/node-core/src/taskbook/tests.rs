//! Unit tests of the task book: signatures, chain validation, persistence
//! and deterministic merge.

use super::{hex::hex_encode, *};
use ed25519_dalek::SigningKey;
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
