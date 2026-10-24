//! Payments due for finalized tasks.

use super::super::*;
use super::support::*;

#[test]
fn finalized_task_pays_the_worker_and_the_counted_verifiers() {
    let mut publisher = Actor::new(90);
    let mut worker = Actor::new(91);
    let mut verifiers: Vec<_> = (92..95).map(Actor::new).collect();
    let (mut book, task) = accepted_task(&mut publisher, &mut worker);
    let result_event = worker.emit(&task, result(1), 5);
    let result_hash = result_event.event_hash();
    book.append(result_event).unwrap();
    for verifier in &mut verifiers {
        verify(
            &mut book,
            &mut publisher,
            verifier,
            &task,
            1,
            &result_hash,
            true,
        );
    }
    assert!(book.settlements_for(&task).is_empty());
    book.append(publisher.emit(&task, TaskEventBody::TaskFinalized { attempt: 1 }, 7))
        .unwrap();

    let due = book.settlements_for(&task);
    // terms(): reward 100, verifier_reward 10, one verification required.
    assert_eq!(due.len(), 2);
    assert_eq!(
        (due[0].role, due[0].payee.as_str(), due[0].amount),
        (SettlementRole::Worker, worker.id.as_str(), 100)
    );
    assert_eq!((due[1].role, due[1].amount), (SettlementRole::Verifier, 10));
    let balances = book.balances();
    assert_eq!(balances[&publisher.id], -110);
    assert_eq!(balances[&worker.id], 100);
}

#[test]
fn finalizing_an_attempt_without_result_does_nothing() {
    let mut publisher = Actor::new(95);
    let mut worker = Actor::new(96);
    let (mut book, task) = accepted_task(&mut publisher, &mut worker);
    book.append(publisher.emit(&task, TaskEventBody::TaskFinalized { attempt: 1 }, 1))
        .unwrap();
    assert_eq!(
        book.task_state(&task, 2).unwrap().status,
        DerivedTaskStatus::Claimed
    );
    assert!(book.settlements().is_empty());

    // Once the result arrives, the pending finalization takes effect.
    book.append(worker.emit(&task, result(1), 3)).unwrap();
    assert_eq!(
        book.task_state(&task, 4).unwrap().status,
        DerivedTaskStatus::Finalized
    );
    assert_eq!(book.settlements_for(&task).len(), 1);
}
