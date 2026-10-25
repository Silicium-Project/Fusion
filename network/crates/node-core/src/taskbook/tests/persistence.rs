//! JSON Lines persistence, including a torn last line.

use std::{
    fs,
    io::Write,
    time::{SystemTime, UNIX_EPOCH},
};

use super::super::*;
use super::support::*;

fn temp_path(name: &str) -> std::path::PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "silicium-taskbook-{name}-{}-{nanos}.jsonl",
        std::process::id()
    ))
}

#[test]
fn persisted_events_reload_including_drained_ones() {
    let path = temp_path("reload");
    let mut publisher = Actor::new(80);
    let task = publisher.task("a");
    let first = publisher.emit(&task, proposed(terms()), 0);
    let second = publisher.emit(&task, TaskEventBody::TaskCancelled, 0);
    let mut book = TaskBook::default();
    assert!(book.receive_persisted(&path, second).unwrap().pending);
    assert_eq!(
        book.receive_persisted(&path, first).unwrap().accepted.len(),
        2
    );

    let reloaded = TaskBook::load(&path).unwrap();
    assert_eq!(reloaded.heads(), book.heads());
    fs::remove_file(path).unwrap();
}

#[test]
fn a_torn_last_line_is_skipped_on_load() {
    let path = temp_path("torn");
    let mut publisher = Actor::new(81);
    let task = publisher.task("a");
    let mut book = TaskBook::default();
    book.append_persisted(&path, publisher.emit(&task, proposed(terms()), 0))
        .unwrap();
    fs::OpenOptions::new()
        .append(true)
        .open(&path)
        .unwrap()
        .write_all(b"{\"version\":2,\"auth")
        .unwrap();

    let (reloaded, report) = TaskBook::load_with_report(&path).unwrap();
    assert!(report.skipped_last_line);
    assert_eq!(reloaded.heads(), book.heads());
    fs::remove_file(path).unwrap();
}

#[test]
fn a_corrupt_line_in_the_middle_still_aborts_the_load() {
    let path = temp_path("corrupt");
    let mut publisher = Actor::new(82);
    let task = publisher.task("a");
    let first = serde_json::to_string(&publisher.emit(&task, proposed(terms()), 0)).unwrap();
    let second =
        serde_json::to_string(&publisher.emit(&task, TaskEventBody::TaskCancelled, 0)).unwrap();
    fs::write(&path, format!("{first}\ngarbage\n{second}\n")).unwrap();
    assert!(TaskBook::load(&path).is_err());
    fs::remove_file(path).unwrap();
}
