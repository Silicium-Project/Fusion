//! Reputation derived from attempts.

use super::super::*;
use super::support::*;

#[test]
fn finalized_and_failed_attempts_shape_each_claimant_record() {
    let mut publisher = Actor::new(130);
    let mut flaky = Actor::new(131);
    let mut reliable = Actor::new(132);
    let (mut book, task) = accepted_task(&mut publisher, &mut flaky);
    book.append(flaky.emit(&task, TaskEventBody::ClaimReleased { attempt: 1 }, 10))
        .unwrap();
    let claim = reliable.emit(&task, TaskEventBody::ClaimProposed { attempt: 2 }, 10);
    let accept = publisher.emit(
        &task,
        TaskEventBody::ClaimAccepted {
            attempt: 2,
            claim: claim.event_hash(),
        },
        10,
    );
    apply(&mut book, [claim, accept]);
    book.append(reliable.emit(&task, result(2), 20)).unwrap();

    // One verification required: not finalized yet, the released attempt
    // already counts against the first claimant.
    let records = book.author_records(30);
    assert_eq!(
        records[&flaky.id],
        AuthorRecord {
            completed: 0,
            failed: 1
        }
    );
    assert_eq!(records[&reliable.id], AuthorRecord::default());
    assert!(records[&flaky.id].score() < AuthorRecord::default().score());

    let mut verifier = Actor::new(133);
    let result_hash = book.task_state(&task, 30).unwrap().attempts[1]
        .result
        .clone()
        .unwrap()
        .event_hash;
    verify(
        &mut book,
        &mut publisher,
        &mut verifier,
        &task,
        2,
        &result_hash,
        true,
    );
    book.append(publisher.emit(&task, TaskEventBody::TaskFinalized { attempt: 2 }, 40))
        .unwrap();
    let records = book.author_records(50);
    assert_eq!(
        records[&reliable.id],
        AuthorRecord {
            completed: 1,
            failed: 0
        }
    );
    assert!((records[&reliable.id].score() - 2.0 / 3.0).abs() < 1e-9);
}
