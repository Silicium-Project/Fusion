//! Publisher decisions on an in-memory task book.

use super::*;
use ed25519_dalek::SigningKey;
use silicium_node_core::taskbook::{EventHeader, PayloadRef, TaskEvent, TaskTerms};

/// Signs the `sequence`-th event of `key`'s chain in `book`.
fn emit(
    book: &mut TaskBook,
    key: &SigningKey,
    task_id: &str,
    body: TaskEventBody,
    at: u64,
) -> String {
    let author = TaskEvent::author_id(key);
    let header = EventHeader {
        sequence: book.next_sequence(&author),
        previous_event_hash: book.head(&author).unwrap_or_default().to_string(),
        issued_at_ms: at,
        task_id: task_id.to_string(),
    };
    let event = TaskEvent::signed(key, header, body);
    let hash = event.event_hash();
    book.append(event).unwrap();
    hash
}

/// Two workers connected to a publisher that does not work itself.
const WORKERS: WorkerView = WorkerView {
    others: 2,
    local_is_worker: false,
};

/// No other worker connected to a publisher that also works.
const ALONE: WorkerView = WorkerView {
    others: 0,
    local_is_worker: true,
};

/// Sweep view at `now` for a node with peers.
fn view(book: &TaskBook, now: u64) -> SweepView<'_> {
    SweepView {
        book,
        me: "observer",
        now,
        records: book.author_records(now),
        workers: WORKERS,
    }
}

fn proposed_task(book: &mut TaskBook, publisher: &SigningKey) -> String {
    let task_id = TaskEvent::task_id_for(&TaskEvent::author_id(publisher), "tile");
    let spec = PayloadRef {
        uri: "silicium/task/v1/tile".to_string(),
        sha256: TaskEvent::payload_hash(b"spec"),
    };
    let terms = TaskTerms {
        lease_ms: 1_000,
        max_attempts: 2,
        verifications_required: 0,
        ..TaskTerms::default()
    };
    emit(
        book,
        publisher,
        &task_id,
        TaskEventBody::TaskProposed { spec, terms },
        0,
    );
    task_id
}

#[test]
fn accepts_the_earliest_claim_then_finalizes_the_result() {
    let publisher = SigningKey::from_bytes(&[1; 32]);
    let late = SigningKey::from_bytes(&[2; 32]);
    let early = SigningKey::from_bytes(&[3; 32]);
    let mut book = TaskBook::default();
    let task = proposed_task(&mut book, &publisher);
    assert!(
        matches!(decide(&view(&book, 0), &task), Some(Decision::Regossip)),
        "unclaimed: announce again"
    );

    emit(
        &mut book,
        &late,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        20,
    );
    let early_claim = emit(
        &mut book,
        &early,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        10,
    );
    let Some(Decision::Sign(accept)) = decide(&view(&book, 30), &task) else {
        panic!("expected an acceptance");
    };
    assert_eq!(
        accept,
        TaskEventBody::ClaimAccepted {
            attempt: 1,
            claim: early_claim
        }
    );
    emit(&mut book, &publisher, &task, accept, 30);
    assert!(decide(&view(&book, 40), &task).is_none());

    let result = PayloadRef {
        uri: "result://tile".to_string(),
        sha256: TaskEvent::payload_hash(b"r"),
    };
    emit(
        &mut book,
        &early,
        &task,
        TaskEventBody::ResultPublished {
            attempt: 1,
            result,
            milestones: Vec::new(),
        },
        50,
    );
    let Some(Decision::Sign(finalize)) = decide(&view(&book, 60), &task) else {
        panic!("expected a finalization");
    };
    assert_eq!(finalize, TaskEventBody::TaskFinalized { attempt: 1 });
    emit(&mut book, &publisher, &task, finalize, 60);
    assert!(matches!(
        decide(&view(&book, 70), &task),
        Some(Decision::Finished)
    ));
}

#[test]
fn a_lapsed_lease_without_new_claims_asks_for_a_retry() {
    let publisher = SigningKey::from_bytes(&[4; 32]);
    let worker = SigningKey::from_bytes(&[5; 32]);
    let mut book = TaskBook::default();
    let task = proposed_task(&mut book, &publisher);
    let claim = emit(
        &mut book,
        &worker,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        0,
    );
    emit(
        &mut book,
        &publisher,
        &task,
        TaskEventBody::ClaimAccepted { attempt: 1, claim },
        0,
    );
    assert!(decide(&view(&book, 500), &task).is_none());
    assert!(matches!(
        decide(&view(&book, 1_500), &task),
        Some(Decision::Regossip)
    ));
}

#[test]
fn a_result_waits_for_an_accepted_verifier_before_finalization() {
    let publisher = SigningKey::from_bytes(&[6; 32]);
    let worker = SigningKey::from_bytes(&[7; 32]);
    let verifier = SigningKey::from_bytes(&[8; 32]);
    let mut book = TaskBook::default();
    let task = TaskEvent::task_id_for(&TaskEvent::author_id(&publisher), "checked");
    let spec = PayloadRef {
        uri: "silicium/task/v1/checked".to_string(),
        sha256: TaskEvent::payload_hash(b"spec"),
    };
    let terms = TaskTerms {
        lease_ms: 10_000,
        verifications_required: 1,
        ..TaskTerms::default()
    };
    emit(
        &mut book,
        &publisher,
        &task,
        TaskEventBody::TaskProposed { spec, terms },
        0,
    );
    let claim = emit(
        &mut book,
        &worker,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        0,
    );
    emit(
        &mut book,
        &publisher,
        &task,
        TaskEventBody::ClaimAccepted { attempt: 1, claim },
        0,
    );
    let result = PayloadRef {
        uri: "result://checked".to_string(),
        sha256: TaskEvent::payload_hash(b"r"),
    };
    let result_event = emit(
        &mut book,
        &worker,
        &task,
        TaskEventBody::ResultPublished {
            attempt: 1,
            result,
            milestones: Vec::new(),
        },
        10,
    );
    assert!(
        matches!(decide(&view(&book, 20), &task), Some(Decision::Regossip)),
        "no verifier yet: announce again"
    );

    let offer = emit(
        &mut book,
        &verifier,
        &task,
        TaskEventBody::VerificationClaimed { attempt: 1 },
        20,
    );
    let Some(Decision::Sign(accept)) = decide(&view(&book, 30), &task) else {
        panic!("expected a verifier acceptance");
    };
    assert_eq!(
        accept,
        TaskEventBody::VerifierAccepted {
            attempt: 1,
            claim: offer
        }
    );
    emit(&mut book, &publisher, &task, accept, 30);
    assert!(decide(&view(&book, 40), &task).is_none());

    emit(
        &mut book,
        &verifier,
        &task,
        TaskEventBody::VerificationPublished {
            attempt: 1,
            result_event,
            approved: true,
        },
        50,
    );
    let Some(Decision::Sign(finalize)) = decide(&view(&book, 60), &task) else {
        panic!("expected a finalization");
    };
    assert_eq!(finalize, TaskEventBody::TaskFinalized { attempt: 1 });
}

#[test]
fn claims_are_ranked_by_reputation_before_age() {
    let publisher = SigningKey::from_bytes(&[9; 32]);
    let flaky = SigningKey::from_bytes(&[10; 32]);
    let newcomer = SigningKey::from_bytes(&[11; 32]);
    let mut book = TaskBook::default();
    let task = proposed_task(&mut book, &publisher);
    emit(
        &mut book,
        &flaky,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        1,
    );
    let newcomer_claim = emit(
        &mut book,
        &newcomer,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        5,
    );
    let mut sweep_view = view(&book, 10);
    sweep_view.records.insert(
        TaskEvent::author_id(&flaky),
        AuthorRecord {
            completed: 0,
            failed: 3,
        },
    );
    let Some(Decision::Sign(accept)) = decide(&sweep_view, &task) else {
        panic!("expected an acceptance");
    };
    assert_eq!(
        accept,
        TaskEventBody::ClaimAccepted {
            attempt: 1,
            claim: newcomer_claim
        }
    );
}

#[test]
fn a_lone_node_may_verify_its_own_result() {
    let publisher = SigningKey::from_bytes(&[12; 32]);
    let mut book = TaskBook::default();
    let task = TaskEvent::task_id_for(&TaskEvent::author_id(&publisher), "solo");
    let spec = PayloadRef {
        uri: "silicium/task/v1/solo".to_string(),
        sha256: TaskEvent::payload_hash(b"spec"),
    };
    let terms = TaskTerms {
        lease_ms: 10_000,
        verifications_required: 1,
        allow_self_verification: true,
        ..TaskTerms::default()
    };
    emit(
        &mut book,
        &publisher,
        &task,
        TaskEventBody::TaskProposed { spec, terms },
        0,
    );
    let claim = emit(
        &mut book,
        &publisher,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        0,
    );
    emit(
        &mut book,
        &publisher,
        &task,
        TaskEventBody::ClaimAccepted { attempt: 1, claim },
        0,
    );
    let result = PayloadRef {
        uri: "result://solo".to_string(),
        sha256: TaskEvent::payload_hash(b"r"),
    };
    let result_body = TaskEventBody::ResultPublished {
        attempt: 1,
        result,
        milestones: Vec::new(),
    };
    emit(&mut book, &publisher, &task, result_body, 10);
    let offer = emit(
        &mut book,
        &publisher,
        &task,
        TaskEventBody::VerificationClaimed { attempt: 1 },
        20,
    );

    assert!(
        matches!(decide(&view(&book, 30), &task), Some(Decision::Regossip)),
        "other workers exist: no self-check"
    );
    let alone = SweepView {
        workers: ALONE,
        ..view(&book, 30)
    };
    let Some(Decision::Sign(accept)) = decide(&alone, &task) else {
        panic!("expected a self-verification acceptance");
    };
    assert_eq!(
        accept,
        TaskEventBody::VerifierAccepted {
            attempt: 1,
            claim: offer
        }
    );
}

#[test]
fn the_publisher_takes_its_own_task_only_when_nobody_else_claims_it() {
    let publisher = SigningKey::from_bytes(&[20; 32]);
    let worker = SigningKey::from_bytes(&[21; 32]);
    let me = TaskEvent::author_id(&publisher);
    let mut book = TaskBook::default();
    let task = proposed_task(&mut book, &publisher);
    let own = emit(
        &mut book,
        &publisher,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        10,
    );
    let at = |book: &TaskBook, now: u64, alone: bool| {
        let view = SweepView {
            me: &me,
            workers: if alone { ALONE } else { WORKERS },
            ..view(book, now)
        };
        match decide(&view, &task) {
            Some(Decision::Sign(TaskEventBody::ClaimAccepted { claim, .. })) => Some(claim),
            _ => None,
        }
    };
    assert_eq!(at(&book, 20, false), None, "others get a chance first");
    assert_eq!(
        at(&book, 20, true),
        Some(own.clone()),
        "alone: no reason to wait"
    );
    assert_eq!(at(&book, 10 + OWN_CLAIM_GRACE_MS, false), Some(own));

    let other = emit(
        &mut book,
        &worker,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        3_000,
    );
    assert_eq!(
        at(&book, 10 + OWN_CLAIM_GRACE_MS, false),
        Some(other.clone())
    );
    assert_eq!(
        at(&book, 3_000, true),
        Some(other),
        "another node is preferred"
    );
}

/// The dev network: an orchestrator (not a worker) publishes, a single
/// desktop worker computes and offers to verify its own result. That worker
/// is the only one on the network, so its offer is accepted.
#[test]
fn a_single_worker_behind_an_orchestrator_may_verify_itself() {
    let orchestrator = SigningKey::from_bytes(&[30; 32]);
    let worker = SigningKey::from_bytes(&[31; 32]);
    let me = TaskEvent::author_id(&orchestrator);
    let mut book = TaskBook::default();
    let task = TaskEvent::task_id_for(&me, "lone");
    let spec = PayloadRef {
        uri: "silicium/task/v1/lone".to_string(),
        sha256: TaskEvent::payload_hash(b"spec"),
    };
    let terms = TaskTerms {
        lease_ms: 10_000,
        verifications_required: 1,
        allow_self_verification: true,
        ..TaskTerms::default()
    };
    emit(
        &mut book,
        &orchestrator,
        &task,
        TaskEventBody::TaskProposed { spec, terms },
        0,
    );
    let claim = emit(
        &mut book,
        &worker,
        &task,
        TaskEventBody::ClaimProposed { attempt: 1 },
        0,
    );
    emit(
        &mut book,
        &orchestrator,
        &task,
        TaskEventBody::ClaimAccepted { attempt: 1, claim },
        0,
    );
    let result = PayloadRef {
        uri: "result://lone".to_string(),
        sha256: TaskEvent::payload_hash(b"r"),
    };
    let result_body = TaskEventBody::ResultPublished {
        attempt: 1,
        result,
        milestones: Vec::new(),
    };
    emit(&mut book, &worker, &task, result_body, 10);
    let offer = emit(
        &mut book,
        &worker,
        &task,
        TaskEventBody::VerificationClaimed { attempt: 1 },
        20,
    );
    let seen_by = |workers: WorkerView| {
        let view = SweepView {
            me: &me,
            workers,
            ..view(&book, 30)
        };
        match decide(&view, &task) {
            Some(Decision::Sign(TaskEventBody::VerifierAccepted { claim, .. })) => Some(claim),
            _ => None,
        }
    };
    let one_worker = WorkerView {
        others: 1,
        local_is_worker: false,
    };
    assert_eq!(seen_by(one_worker), Some(offer), "lone worker");
    let two_workers = WorkerView {
        others: 2,
        local_is_worker: false,
    };
    assert_eq!(seen_by(two_workers), None, "another worker must verify");
}
