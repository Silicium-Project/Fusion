//! Signatures, chain links, equivocation and per-task limits.

use super::super::*;
use super::support::*;

#[test]
fn signed_event_verifies_and_tampering_is_detected() {
    let mut publisher = Actor::new(1);
    let task = publisher.task("a");
    let event = publisher.emit(&task, proposed(terms()), 5);
    event.verify().unwrap();
    assert_eq!(event.event_hash().len(), 64);

    let mut tampered = event.clone();
    tampered.issued_at_ms = 6;
    assert_eq!(tampered.verify(), Err(TaskBookError::InvalidSignature));
}

#[test]
fn chain_requires_consecutive_sequences_and_predecessor() {
    let mut actor = Actor::new(2);
    let task = actor.task("a");
    let first = actor.emit(&task, proposed(terms()), 0);
    let second = actor.emit(&task, TaskEventBody::TaskCancelled, 0);
    let mut book = TaskBook::default();
    assert!(matches!(
        book.append(second.clone()),
        Err(TaskBookError::SequenceGap { .. })
    ));
    book.append(first.clone()).unwrap();
    assert_eq!(book.append(first.clone()).unwrap(), first.event_hash());
    book.append(second).unwrap();
    assert_eq!(book.next_sequence(&actor.id), 3);
}

#[test]
fn two_versions_of_one_event_mark_the_author_as_equivocating() {
    let mut actor = Actor::new(3);
    let mut twin = Actor::new(3);
    let task = actor.task("a");
    let original = actor.emit(&task, proposed(terms()), 0);
    let fork = twin.emit(&task, proposed(terms()), 1);
    let mut book = TaskBook::default();
    book.append(original).unwrap();
    assert!(matches!(
        book.append(fork),
        Err(TaskBookError::Equivocation(_))
    ));
    assert!(book.equivocators().contains(&actor.id));
    // The equivocator's tasks are ignored from then on.
    assert!(book.task_state(&task, 0).is_none());
}

#[test]
fn one_author_cannot_flood_a_task() {
    let mut publisher = Actor::new(4);
    let mut spammer = Actor::new(5);
    let task = publisher.task("a");
    let mut book = TaskBook::default();
    book.append(publisher.emit(&task, proposed(terms()), 0))
        .unwrap();
    for _ in 0..MAX_EVENTS_PER_AUTHOR_PER_TASK {
        book.append(spammer.emit(&task, TaskEventBody::ClaimProposed { attempt: 1 }, 0))
            .unwrap();
    }
    let extra = spammer.emit(&task, TaskEventBody::ClaimProposed { attempt: 1 }, 0);
    assert_eq!(book.append(extra), Err(TaskBookError::TooManyEvents));
}

#[test]
fn malformed_bodies_and_task_ids_are_refused() {
    let mut actor = Actor::new(6);
    let bad_attempt = actor.emit(
        &actor.task("a"),
        TaskEventBody::ClaimProposed { attempt: 0 },
        0,
    );
    assert!(matches!(
        bad_attempt.verify(),
        Err(TaskBookError::InvalidBody(_))
    ));

    let mut other = Actor::new(7);
    let bad_id = other.emit("not-a-task-id", TaskEventBody::TaskCancelled, 0);
    assert_eq!(bad_id.verify(), Err(TaskBookError::InvalidTaskId));

    let mut zero_lease = terms();
    zero_lease.lease_ms = 0;
    let mut third = Actor::new(8);
    let event = third.emit(&third.task("a"), proposed(zero_lease), 0);
    assert!(matches!(event.verify(), Err(TaskBookError::InvalidBody(_))));
}
