//! Roles: only the publisher decides, only the accepted claimant reports,
//! nobody verifies itself, and claims never win by hash.

use super::super::*;
use super::support::*;

#[test]
fn only_the_key_owning_the_identifier_can_propose_the_task() {
    let publisher = Actor::new(10);
    let mut intruder = Actor::new(11);
    let hijack = intruder.emit(&publisher.task("tile-1"), proposed(terms()), 0);
    assert_eq!(hijack.verify(), Err(TaskBookError::NotTaskOwner));
}

#[test]
fn finalize_and_cancel_from_other_authors_are_ignored() {
    let mut publisher = Actor::new(12);
    let mut worker = Actor::new(13);
    let mut intruder = Actor::new(14);
    let (mut book, task) = accepted_task(&mut publisher, &mut worker);
    apply(
        &mut book,
        [
            worker.emit(&task, result(1), 10),
            intruder.emit(&task, TaskEventBody::TaskFinalized { attempt: 1 }, 10),
            intruder.emit(&task, TaskEventBody::TaskCancelled, 10),
        ],
    );
    let state = book.task_state(&task, 20).unwrap();
    assert_eq!(state.status, DerivedTaskStatus::Completed);
    assert!(book.settlements_for(&task).is_empty());
}

#[test]
fn claims_are_only_offers_until_the_publisher_accepts_one() {
    let mut publisher = Actor::new(15);
    let task = publisher.task("tile-1");
    let mut book = TaskBook::default();
    book.append(publisher.emit(&task, proposed(terms()), 0))
        .unwrap();
    let mut claimants: Vec<_> = (20..30).map(Actor::new).collect();
    for claimant in &mut claimants {
        book.append(claimant.emit(&task, TaskEventBody::ClaimProposed { attempt: 1 }, 0))
            .unwrap();
    }
    let state = book.task_state(&task, 0).unwrap();
    assert_eq!(state.status, DerivedTaskStatus::Open);
    assert_eq!(state.claimant(), None);
    let open = book.open_claims(&task, 0);
    assert_eq!(open.len(), 10);

    let chosen = open[3].clone();
    book.append(publisher.emit(
        &task,
        TaskEventBody::ClaimAccepted {
            attempt: 1,
            claim: chosen.event_hash,
        },
        0,
    ))
    .unwrap();
    let state = book.task_state(&task, 0).unwrap();
    assert_eq!(state.status, DerivedTaskStatus::Claimed);
    assert_eq!(state.claimant(), Some(chosen.author.as_str()));
}

#[test]
fn results_and_renewals_from_others_than_the_claimant_are_ignored() {
    let mut publisher = Actor::new(16);
    let mut worker = Actor::new(17);
    let mut intruder = Actor::new(18);
    let (mut book, task) = accepted_task(&mut publisher, &mut worker);
    apply(
        &mut book,
        [
            intruder.emit(&task, result(1), 1),
            intruder.emit(&task, TaskEventBody::LeaseRenewed { attempt: 1 }, 1),
            intruder.emit(&task, TaskEventBody::ClaimReleased { attempt: 1 }, 1),
        ],
    );
    let state = book.task_state(&task, 500).unwrap();
    assert_eq!(state.status, DerivedTaskStatus::Claimed);
    assert_eq!(state.attempts[0].renewals, 0);
    assert!(state.attempts[0].result.is_none());
}

#[test]
fn a_claimant_cannot_verify_its_own_result() {
    let mut publisher = Actor::new(19);
    let mut worker = Actor::new(40);
    let (mut book, task) = accepted_task(&mut publisher, &mut worker);
    let result_event = worker.emit(&task, result(1), 5);
    let result_hash = result_event.event_hash();
    let self_check = worker.emit(
        &task,
        TaskEventBody::VerificationPublished {
            attempt: 1,
            result_event: result_hash,
            approved: true,
        },
        6,
    );
    apply(&mut book, [result_event, self_check]);
    let state = book.task_state(&task, 10).unwrap();
    assert_eq!(state.status, DerivedTaskStatus::Completed);
    assert!(
        state.attempts[0]
            .result
            .as_ref()
            .unwrap()
            .approvals
            .is_empty()
    );
}

#[test]
fn accepting_a_claim_of_another_task_or_attempt_is_invalid() {
    let mut publisher = Actor::new(41);
    let mut worker = Actor::new(42);
    let task = publisher.task("a");
    let other = publisher.task("b");
    let mut book = TaskBook::default();
    let foreign_claim = worker.emit(&other, TaskEventBody::ClaimProposed { attempt: 1 }, 0);
    let wrong_attempt = worker.emit(&task, TaskEventBody::ClaimProposed { attempt: 2 }, 0);
    apply(
        &mut book,
        [
            publisher.emit(&task, proposed(terms()), 0),
            publisher.emit(
                &task,
                TaskEventBody::ClaimAccepted {
                    attempt: 1,
                    claim: foreign_claim.event_hash(),
                },
                0,
            ),
            publisher.emit(
                &task,
                TaskEventBody::ClaimAccepted {
                    attempt: 1,
                    claim: wrong_attempt.event_hash(),
                },
                0,
            ),
            foreign_claim,
            wrong_attempt,
        ],
    );
    assert_eq!(
        book.task_state(&task, 0).unwrap().status,
        DerivedTaskStatus::Open
    );
}
