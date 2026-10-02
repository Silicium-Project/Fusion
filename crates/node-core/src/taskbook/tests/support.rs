//! Test helpers: an [`Actor`] owns a key and its own event chain.

use ed25519_dalek::SigningKey;

use super::super::*;

/// A peer with a signing key that keeps track of its chain head.
pub struct Actor {
    key: SigningKey,
    pub id: String,
    sequence: u64,
    head: String,
}

impl Actor {
    pub fn new(seed: u8) -> Self {
        let key = SigningKey::from_bytes(&[seed; 32]);
        Self {
            id: TaskEvent::author_id(&key),
            key,
            sequence: 0,
            head: String::new(),
        }
    }

    /// Signs the next event of this actor's chain.
    pub fn emit(&mut self, task_id: &str, body: TaskEventBody, issued_at_ms: u64) -> TaskEvent {
        self.sequence += 1;
        let event = TaskEvent::signed(
            &self.key,
            EventHeader {
                sequence: self.sequence,
                previous_event_hash: self.head.clone(),
                issued_at_ms,
                task_id: task_id.to_string(),
            },
            body,
        );
        self.head = event.event_hash();
        event
    }

    /// Task identifier owned by this actor.
    pub fn task(&self, name: &str) -> String {
        TaskEvent::task_id_for(&self.id, name)
    }
}

pub fn payload(uri: &str) -> PayloadRef {
    PayloadRef {
        uri: uri.to_string(),
        sha256: TaskEvent::payload_hash(uri.as_bytes()),
    }
}

pub fn terms() -> TaskTerms {
    TaskTerms {
        lease_ms: 1_000,
        max_renewals: 2,
        max_attempts: 2,
        verifications_required: 1,
        reward: 100,
        verifier_reward: 10,
    }
}

pub fn proposed(terms: TaskTerms) -> TaskEventBody {
    TaskEventBody::TaskProposed {
        spec: payload("silicium/task/v1/spec"),
        terms,
    }
}

pub fn result(attempt: u32) -> TaskEventBody {
    TaskEventBody::ResultPublished {
        attempt,
        result: payload("result://tile"),
    }
}

/// Appends every event to `book`, panicking on refusal.
pub fn apply(book: &mut TaskBook, events: impl IntoIterator<Item = TaskEvent>) {
    for event in events {
        book.append(event).expect("event accepted");
    }
}

/// Publisher proposes, worker claims attempt 1, publisher accepts at t=0.
/// Returns (book, task id).
pub fn accepted_task(publisher: &mut Actor, worker: &mut Actor) -> (TaskBook, String) {
    let task = publisher.task("tile-1");
    let mut book = TaskBook::default();
    let proposal = publisher.emit(&task, proposed(terms()), 0);
    let claim = worker.emit(&task, TaskEventBody::ClaimProposed { attempt: 1 }, 0);
    let accept = publisher.emit(
        &task,
        TaskEventBody::ClaimAccepted {
            attempt: 1,
            claim: claim.event_hash(),
        },
        0,
    );
    apply(&mut book, [proposal, claim, accept]);
    (book, task)
}
