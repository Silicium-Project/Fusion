//! Out-of-order reception, gap reporting and the order independence of
//! derived states.

use super::super::*;
use super::support::*;

#[test]
fn events_ahead_of_their_predecessor_wait_then_drain() {
    let mut publisher = Actor::new(70);
    let task = publisher.task("a");
    let first = publisher.emit(&task, proposed(terms()), 0);
    let second = publisher.emit(&task, TaskEventBody::TaskCancelled, 0);
    let mut book = TaskBook::default();

    let waiting = book.receive(second.clone()).unwrap();
    assert!(waiting.pending);
    assert!(waiting.accepted.is_empty());
    let missing = book.missing_events();
    assert_eq!(missing.len(), 1);
    assert_eq!(
        (missing[0].after_sequence, missing[0].first_waiting),
        (0, 2)
    );

    let unblocked = book.receive(first.clone()).unwrap();
    assert_eq!(
        unblocked.accepted,
        vec![first.event_hash(), second.event_hash()]
    );
    assert_eq!(book.pending_count(), 0);
    assert!(book.missing_events().is_empty());
    assert_eq!(
        book.task_state(&task, 0).unwrap().status,
        DerivedTaskStatus::Cancelled
    );
}

#[test]
fn a_peer_can_serve_the_missing_range() {
    let mut publisher = Actor::new(71);
    let task = publisher.task("a");
    let events: Vec<_> = (0..5)
        .map(|index| {
            if index == 0 {
                publisher.emit(&task, proposed(terms()), 0)
            } else {
                publisher.emit(&task, TaskEventBody::ClaimProposed { attempt: 1 }, 0)
            }
        })
        .collect();
    let mut full = TaskBook::default();
    apply(&mut full, events.clone());

    let mut partial = TaskBook::default();
    partial.receive(events[0].clone()).unwrap();
    partial.receive(events[4].clone()).unwrap();
    let gap = &partial.missing_events()[0];
    let answer = full.events_for_author_after(&gap.author, gap.after_sequence);
    assert_eq!(partial.merge(answer).unwrap(), 4);
    assert_eq!(partial.next_sequence(&publisher.id), 6);
}

#[test]
fn derived_state_does_not_depend_on_arrival_order() {
    let mut publisher = Actor::new(72);
    let mut worker = Actor::new(73);
    let mut verifier = Actor::new(74);
    let task = publisher.task("a");
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
    let result_event = worker.emit(&task, result(1), 5);
    let offer = verifier.emit(&task, TaskEventBody::VerificationClaimed { attempt: 1 }, 6);
    let accept_verifier = publisher.emit(
        &task,
        TaskEventBody::VerifierAccepted {
            attempt: 1,
            claim: offer.event_hash(),
        },
        6,
    );
    let verdict = verifier.emit(
        &task,
        TaskEventBody::VerificationPublished {
            attempt: 1,
            result_event: result_event.event_hash(),
            approved: true,
        },
        7,
    );
    let finalize = publisher.emit(&task, TaskEventBody::TaskFinalized { attempt: 1 }, 7);
    let events = [
        proposal,
        claim,
        accept,
        result_event,
        offer,
        accept_verifier,
        verdict,
        finalize,
    ];

    let mut forward = TaskBook::default();
    for event in events.iter().cloned() {
        forward.receive(event).unwrap();
    }
    let mut backward = TaskBook::default();
    for event in events.iter().rev().cloned() {
        backward.receive(event).unwrap();
    }
    assert_eq!(
        forward.task_state(&task, 10),
        backward.task_state(&task, 10)
    );
    assert_eq!(
        forward.task_state(&task, 10).unwrap().status,
        DerivedTaskStatus::Finalized
    );
}

#[test]
fn a_fork_waiting_in_the_buffer_is_detected() {
    let mut actor = Actor::new(75);
    let mut twin = Actor::new(75);
    let task = actor.task("a");
    let _first = actor.emit(&task, proposed(terms()), 0);
    let second = actor.emit(&task, TaskEventBody::TaskCancelled, 0);
    let _twin_first = twin.emit(&task, proposed(terms()), 1);
    let twin_second = twin.emit(&task, TaskEventBody::TaskCancelled, 1);
    let mut book = TaskBook::default();
    book.receive(second).unwrap();
    assert!(matches!(
        book.receive(twin_second),
        Err(TaskBookError::Equivocation(_))
    ));
    assert_eq!(book.pending_count(), 0);
}

#[test]
fn the_waiting_buffer_is_bounded_per_author() {
    let mut actor = Actor::new(76);
    let task = actor.task("a");
    let _first = actor.emit(&task, proposed(terms()), 0);
    let mut book = TaskBook::default();
    for _ in 0..MAX_PENDING_PER_AUTHOR {
        let event = actor.emit(&task, TaskEventBody::ClaimProposed { attempt: 1 }, 0);
        assert!(book.receive(event).unwrap().pending);
    }
    let overflow = actor.emit(&task, TaskEventBody::ClaimProposed { attempt: 1 }, 0);
    assert_eq!(book.receive(overflow), Err(TaskBookError::PendingFull));
}
