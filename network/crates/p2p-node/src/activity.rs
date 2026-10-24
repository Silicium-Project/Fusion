//! What this node is doing, for the desktop app: the tasks it is working on
//! right now (sent in its heartbeat) and a journal of its work
//! (`<export dir>/node.events.ndjson`, one JSON object per line).
//!
//! The journal uses the event kinds the desktop app already displays:
//! `task_received`, `task_started`, then `task` with `ok` and `duration_ms`
//! when the work ends. `role` is `compute` for a rendered fragment and
//! `verify` for a verification of another node's result.

use crate::task::utc_now;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    env,
    fs::{self, OpenOptions},
    io::Write,
    path::PathBuf,
    sync::{Arc, Mutex},
    time::Instant,
};

/// The journal is cut down to its most recent half beyond this size.
const MAX_JOURNAL_BYTES: u64 = 2 * 1024 * 1024;

/// Kind of work, as shown by the app.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Role {
    /// Rendering a fragment.
    Compute,
    /// Re-rendering sampled blocks of another node's fragment.
    Verify,
}

impl Role {
    fn name(self) -> &'static str {
        match self {
            Role::Compute => "compute",
            Role::Verify => "verify",
        }
    }

    fn activity(self) -> &'static str {
        match self {
            Role::Compute => "fragment",
            Role::Verify => "verification",
        }
    }
}

/// One piece of work in progress.
#[derive(Debug, Clone)]
struct Running {
    role: Role,
    started: Instant,
    started_utc: String,
}

/// Activity of this node: work in progress and the journal file.
#[derive(Clone)]
pub(crate) struct ActivityLog {
    path: Option<PathBuf>,
    running: Arc<Mutex<BTreeMap<(String, &'static str), Running>>>,
}

impl ActivityLog {
    /// Journal in `SILICIUM_EXPORT_DIR` (none when the variable is unset).
    pub(crate) fn from_env() -> Self {
        let path = env::var("SILICIUM_EXPORT_DIR")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .map(|dir| PathBuf::from(dir).join("node.events.ndjson"));
        Self::at(path)
    }

    /// Journal at `path` (`None`: only the work in progress is tracked).
    pub(crate) fn at(path: Option<PathBuf>) -> Self {
        Self {
            path,
            running: Arc::default(),
        }
    }

    /// A task was received from the network and will be claimed.
    pub(crate) fn received(&self, task_id: &str) {
        self.append(json!({
            "kind": "task_received",
            "item_id": task_id,
            "role": Role::Compute.name(),
            "fragment_index": fragment_index(task_id),
            "ok": true,
            "timestamp_utc": utc_now(),
        }));
    }

    /// Work on `task_id` starts.
    pub(crate) fn started(&self, task_id: &str, role: Role) {
        let started_utc = utc_now();
        if let Ok(mut running) = self.running.lock() {
            running.insert(
                (task_id.to_string(), role.name()),
                Running {
                    role,
                    started: Instant::now(),
                    started_utc: started_utc.clone(),
                },
            );
        }
        self.append(json!({
            "kind": "task_started",
            "item_id": task_id,
            "role": role.name(),
            "activity": role.activity(),
            "fragment_index": fragment_index(task_id),
            "ok": true,
            "timestamp_utc": started_utc,
        }));
    }

    /// Work on `task_id` ended, successfully or not.
    pub(crate) fn finished(&self, task_id: &str, role: Role, ok: bool) {
        let running = self
            .running
            .lock()
            .ok()
            .and_then(|mut running| running.remove(&(task_id.to_string(), role.name())));
        let duration_ms = running
            .map(|item| item.started.elapsed().as_millis() as u64)
            .unwrap_or_default();
        self.append(json!({
            "kind": "task",
            "item_id": task_id,
            "role": role.name(),
            "activity": role.activity(),
            "fragment_index": fragment_index(task_id),
            "ok": ok,
            "duration_ms": duration_ms,
            "timestamp_utc": utc_now(),
        }));
    }

    /// Work in progress, in the heartbeat format read by the app.
    pub(crate) fn active_tasks(&self) -> Vec<Value> {
        let Ok(running) = self.running.lock() else {
            return Vec::new();
        };
        running
            .iter()
            .map(|((task_id, _), item)| {
                json!({
                    "item_id": task_id,
                    "role": item.role.name(),
                    "activity": item.role.activity(),
                    "workload": "raytracer",
                    "fragment_index": fragment_index(task_id),
                    "phase": "executing",
                    "elapsed_ms": item.started.elapsed().as_millis() as u64,
                    "queued_utc": item.started_utc,
                })
            })
            .collect()
    }

    fn append(&self, event: Value) {
        let Some(path) = &self.path else {
            return;
        };
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        trim_journal(path);
        let line = format!("{event}\n");
        let written = OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .and_then(|mut file| file.write_all(line.as_bytes()));
        if let Err(err) = written {
            println!(" Activity journal not written: {err}");
        }
    }
}

/// Keeps the most recent half of the journal once it is too large.
fn trim_journal(path: &PathBuf) {
    let too_large = fs::metadata(path).is_ok_and(|meta| meta.len() > MAX_JOURNAL_BYTES);
    if !too_large {
        return;
    }
    let Ok(content) = fs::read_to_string(path) else {
        return;
    };
    let lines: Vec<&str> = content.lines().collect();
    let kept = lines[lines.len() / 2..].join("\n") + "\n";
    let _ = fs::write(path, kept);
}

/// Fragment number of a fragment task id (`<job>.fNNN`), else null.
fn fragment_index(task_id: &str) -> Value {
    task_id
        .rsplit_once(".f")
        .and_then(|(_, value)| value.parse::<u32>().ok())
        .map_or(Value::Null, Value::from)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn work_in_progress_and_journal_follow_the_task() {
        let dir = std::env::temp_dir().join(format!("silicium-activity-{}", std::process::id()));
        let path = dir.join("node.events.ndjson");
        let _ = fs::remove_file(&path);
        let log = ActivityLog::at(Some(path.clone()));
        log.received("abc.job.f003");
        log.started("abc.job.f003", Role::Compute);
        let active = log.active_tasks();
        assert_eq!(active.len(), 1);
        assert_eq!(active[0]["fragment_index"], 3);
        assert_eq!(active[0]["role"], "compute");
        log.finished("abc.job.f003", Role::Compute, true);
        assert!(log.active_tasks().is_empty());

        let journal = fs::read_to_string(&path).unwrap();
        let kinds: Vec<Value> = journal
            .lines()
            .map(|line| serde_json::from_str::<Value>(line).unwrap()["kind"].clone())
            .collect();
        assert_eq!(kinds, ["task_received", "task_started", "task"]);
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn a_node_may_compute_and_verify_the_same_task() {
        let log = ActivityLog::at(None);
        log.started("abc.job.f000", Role::Compute);
        log.started("abc.job.f000", Role::Verify);
        assert_eq!(log.active_tasks().len(), 2);
        log.finished("abc.job.f000", Role::Verify, true);
        assert_eq!(log.active_tasks()[0]["role"], "compute");
    }
}
