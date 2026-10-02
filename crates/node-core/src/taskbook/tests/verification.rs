//! Cross-peer verification: offers, the publisher's acceptance, verdicts
//! that count, verifier slots and the milestone sample.

use super::super::*;
use super::support::*;

/// Accepted task with a published result; returns (book, task, result hash).
fn completed(publisher: &mut Actor, worker: &mut Actor) -> (TaskBook, String, String) {
    let (mut book, task) = accepted_task(publisher, worker);
    let result_event = worker.emit(&task, result(1), 5);
    let hash = result_event.event_hash();
    book.append(result_event).unwrap();
    (book, task, hash)
}

#[test]
fn verdicts_from_peers_the_publisher_did_not_accept_are_ignored() {
    let mut publisher = Actor::new(100);
    let mut worker = Actor::new(101);
    let mut stranger = Actor::new(102);
    let (mut book, task, result_hash) = completed(&mut publisher, &mut worker);
    for approved in [true, false] {
        book.append(stranger.emit(
            &task,
            TaskEventBody::VerificationPublished {
                attempt: 1,
                result_event: result_hash.clone(),
                approved,
            },
            6,
        ))
        .unwrap();
    }
    let state = book.task_state(&task, 10).unwrap();
    assert_eq!(state.status, DerivedTaskStatus::Completed);
    let result = state.attempts[0].result.as_ref().unwrap();
    assert!(result.approvals.is_empty() && result.rejections.is_empty());
    assert_eq!(result.milestones.len(), 10);
}

#[test]
fn an_accepted_verifier_approves_and_the_task_is_verified() {
    let mut publisher = Actor::new(103);
    let mut worker = Actor::new(104);
    let mut verifier = Actor::new(105);
    let (mut book, task, result_hash) = completed(&mut publisher, &mut worker);
    assert_eq!(book.verification_slots_open(&task, 10), 1);
    verify(
        &mut book,
        &mut publisher,
        &mut verifier,
        &task,
        1,
        &result_hash,
        true,
    );
    let state = book.task_state(&task, 10).unwrap();
    assert_eq!(state.status, DerivedTaskStatus::Verified);
    assert_eq!(state.attempts[0].verifiers[0].verdict, Some(true));
    assert_eq!(book.verification_slots_open(&task, 10), 0);
}

#[test]
fn the_claimant_cannot_be_accepted_as_its_own_verifier() {
    let mut publisher = Actor::new(106);
    let mut worker = Actor::new(107);
    let (mut book, task, result_hash) = completed(&mut publisher, &mut worker);
    let offer = worker.emit(&task, TaskEventBody::VerificationClaimed { attempt: 1 }, 6);
    assert!(book.open_verifications(&task, 6).is_empty());
    let accept = publisher.emit(
        &task,
        TaskEventBody::VerifierAccepted {
            attempt: 1,
            claim: offer.event_hash(),
        },
        6,
    );
    let verdict = worker.emit(
        &task,
        TaskEventBody::VerificationPublished {
            attempt: 1,
            result_event: result_hash,
            approved: true,
        },
        7,
    );
    apply(&mut book, [offer, accept, verdict]);
    let state = book.task_state(&task, 10).unwrap();
    assert!(state.attempts[0].verifiers.is_empty());
    assert_eq!(state.status, DerivedTaskStatus::Completed);
}

#[test]
fn open_offers_exclude_accepted_verifiers_and_a_silent_verifier_frees_its_slot() {
    let mut publisher = Actor::new(108);
    let mut worker = Actor::new(109);
    let mut silent = Actor::new(110);
    let mut backup = Actor::new(111);
    let (mut book, task, _) = completed(&mut publisher, &mut worker);
    let offer = silent.emit(&task, TaskEventBody::VerificationClaimed { attempt: 1 }, 6);
    let offer_hash = offer.event_hash();
    book.append(offer).unwrap();
    book.append(backup.emit(&task, TaskEventBody::VerificationClaimed { attempt: 1 }, 6))
        .unwrap();
    assert_eq!(book.open_verifications(&task, 6).len(), 2);
    book.append(publisher.emit(
        &task,
        TaskEventBody::VerifierAccepted {
            attempt: 1,
            claim: offer_hash,
        },
        10,
    ))
    .unwrap();
    let open = book.open_verifications(&task, 20);
    assert_eq!(open.len(), 1);
    assert_eq!(open[0].author, backup.id);
    // terms(): lease 1 000 ms; the silent verifier holds its slot until then.
    assert_eq!(book.verification_slots_open(&task, 1_010), 0);
    assert_eq!(book.verification_slots_open(&task, 1_011), 1);
}

#[test]
fn a_verdict_on_another_result_does_not_count() {
    let mut publisher = Actor::new(112);
    let mut worker = Actor::new(113);
    let mut verifier = Actor::new(114);
    let (mut book, task, _) = completed(&mut publisher, &mut worker);
    verify(
        &mut book,
        &mut publisher,
        &mut verifier,
        &task,
        1,
        &"ab".repeat(32),
        false,
    );
    let state = book.task_state(&task, 10).unwrap();
    assert_eq!(state.status, DerivedTaskStatus::Completed);
    assert_eq!(state.attempts[0].verifiers[0].verdict, None);
}

#[test]
fn the_milestone_sample_is_deterministic_and_seed_dependent() {
    let all = milestones();
    assert_eq!(verification_sample_count(all.len()), 2);
    assert_eq!(verification_sample_count(1), 1);
    assert_eq!(verification_sample_count(100), 8);
    assert_eq!(verification_sample_count(0), 0);
    let first = sample_milestones(&all, "seed-a", 3);
    assert_eq!(first, sample_milestones(&all, "seed-a", 3));
    let indexes = |sample: &[&MilestoneSample]| sample.iter().map(|m| m.index).collect::<Vec<_>>();
    let seeds_differ = (0..20)
        .any(|n| indexes(&sample_milestones(&all, &format!("seed-{n}"), 3)) != indexes(&first));
    assert!(seeds_differ);
}

#[test]
fn invalid_milestones_are_refused() {
    let mut worker = Actor::new(115);
    let mut bad = milestones();
    bad[0].y_end = bad[0].y_start;
    let event = worker.emit(
        &worker.task("a"),
        TaskEventBody::ResultPublished {
            attempt: 1,
            result: payload("result://x"),
            milestones: bad,
        },
        0,
    );
    assert!(matches!(event.verify(), Err(TaskBookError::InvalidBody(_))));
}
