//! Leases, renewals, release, rejection and retries.

use super::super::*;
use super::support::*;

#[test]
fn lease_expires_without_renewal_and_opens_the_next_attempt() {
    let mut publisher = Actor::new(50);
    let mut worker = Actor::new(51);
    let (book, task) = accepted_task(&mut publisher, &mut worker);
    let running = book.task_state(&task, 1_000).unwrap();
    assert_eq!(running.status, DerivedTaskStatus::Claimed);
    assert_eq!(running.attempts[0].lease_expires_at_ms, 1_000);

    let lapsed = book.task_state(&task, 1_001).unwrap();
    assert_eq!(lapsed.status, DerivedTaskStatus::LeaseExpired);
    assert_eq!(lapsed.next_attempt, Some(2));
}

#[test]
fn renewals_extend_the_lease_up_to_the_allowed_count() {
    let mut publisher = Actor::new(52);
    let mut worker = Actor::new(53);
    let (mut book, task) = accepted_task(&mut publisher, &mut worker);
    for at in [500, 1_500, 2_500] {
        book.append(worker.emit(&task, TaskEventBody::LeaseRenewed { attempt: 1 }, at))
            .unwrap();
    }
    let state = book.task_state(&task, 2_900).unwrap();
    // terms(): max_renewals = 2, so the third renewal does not count.
    assert_eq!(state.attempts[0].renewals, 2);
    assert_eq!(state.attempts[0].lease_expires_at_ms, 3_000);
    assert_eq!(state.status, DerivedTaskStatus::Claimed);
    assert_eq!(
        book.task_state(&task, 3_001).unwrap().status,
        DerivedTaskStatus::LeaseExpired
    );
}

#[test]
fn a_released_attempt_is_retried_by_another_peer() {
    let mut publisher = Actor::new(54);
    let mut worker = Actor::new(55);
    let mut second = Actor::new(56);
    let (mut book, task) = accepted_task(&mut publisher, &mut worker);
    book.append(worker.emit(&task, TaskEventBody::ClaimReleased { attempt: 1 }, 10))
        .unwrap();
    let released = book.task_state(&task, 20).unwrap();
    assert_eq!(released.status, DerivedTaskStatus::Released);
    assert_eq!(released.next_attempt, Some(2));

    // The previous claimant may not claim again; the newcomer may.
    book.append(worker.emit(&task, TaskEventBody::ClaimProposed { attempt: 2 }, 20))
        .unwrap();
    let claim = second.emit(&task, TaskEventBody::ClaimProposed { attempt: 2 }, 20);
    let claim_hash = claim.event_hash();
    book.append(claim).unwrap();
    let open = book.open_claims(&task, 20);
    assert_eq!(open.len(), 1);
    assert_eq!(open[0].author, second.id);

    book.append(publisher.emit(
        &task,
        TaskEventBody::ClaimAccepted {
            attempt: 2,
            claim: claim_hash,
        },
        30,
    ))
    .unwrap();
    let retried = book.task_state(&task, 40).unwrap();
    assert_eq!(retried.status, DerivedTaskStatus::Claimed);
    assert_eq!(retried.claimant(), Some(second.id.as_str()));
    assert_eq!(retried.attempts[1].lease_expires_at_ms, 1_030);
}

#[test]
fn a_rejected_result_fails_the_attempt_and_exhausted_attempts_fail_the_task() {
    let mut publisher = Actor::new(57);
    let mut worker = Actor::new(58);
    let mut verifier = Actor::new(59);
    let mut second = Actor::new(60);
    let (mut book, task) = accepted_task(&mut publisher, &mut worker);
    let first_result = worker.emit(&task, result(1), 5);
    let verdict = verifier.emit(
        &task,
        TaskEventBody::VerificationPublished {
            attempt: 1,
            result_event: first_result.event_hash(),
            approved: false,
        },
        6,
    );
    apply(&mut book, [first_result, verdict]);
    let rejected = book.task_state(&task, 10).unwrap();
    assert_eq!(rejected.status, DerivedTaskStatus::Rejected);
    assert_eq!(rejected.next_attempt, Some(2));

    let claim = second.emit(&task, TaskEventBody::ClaimProposed { attempt: 2 }, 10);
    let accept = publisher.emit(
        &task,
        TaskEventBody::ClaimAccepted {
            attempt: 2,
            claim: claim.event_hash(),
        },
        10,
    );
    apply(&mut book, [claim, accept]);
    let failed = book.task_state(&task, 5_000).unwrap();
    // terms(): max_attempts = 2 and the second lease lapsed.
    assert_eq!(failed.status, DerivedTaskStatus::Failed);
    assert_eq!(failed.next_attempt, None);
}

#[test]
fn a_late_result_still_counts_while_no_newer_attempt_is_accepted() {
    let mut publisher = Actor::new(61);
    let mut worker = Actor::new(62);
    let (mut book, task) = accepted_task(&mut publisher, &mut worker);
    book.append(worker.emit(&task, result(1), 5_000)).unwrap();
    assert_eq!(
        book.task_state(&task, 6_000).unwrap().status,
        DerivedTaskStatus::Completed
    );
}

#[test]
fn an_acceptance_beyond_max_attempts_or_out_of_order_is_ignored() {
    let mut publisher = Actor::new(63);
    let mut worker = Actor::new(64);
    let task = publisher.task("a");
    let mut book = TaskBook::default();
    let claim = worker.emit(&task, TaskEventBody::ClaimProposed { attempt: 2 }, 0);
    apply(
        &mut book,
        [
            publisher.emit(&task, proposed(terms()), 0),
            publisher.emit(
                &task,
                TaskEventBody::ClaimAccepted {
                    attempt: 2,
                    claim: claim.event_hash(),
                },
                0,
            ),
            claim,
        ],
    );
    assert_eq!(
        book.task_state(&task, 0).unwrap().status,
        DerivedTaskStatus::Open
    );
}
