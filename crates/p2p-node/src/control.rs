//! Durable control-plane records used by the BackEnd compatibility API.
//!
//! The task book remains the source of truth for lifecycle decisions. This
//! small registry only remembers the original site job id and the submitted
//! task envelope, so the BackEnd can query the Rust node without knowing the
//! task-book author's key or the fragment suffixes.

use crate::{storage::TaskBookState, task::NetworkTask};
use serde::{Deserialize, Serialize};
use silicium_node_core::taskbook::{DerivedTaskState, DerivedTaskStatus};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Entry {
    root_job_id: String,
    task: NetworkTask,
    required_roles: Vec<String>,
    created_unix: i64,
    updated_unix: i64,
    /// Why the task could not be published (it never reaches the task book).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    failure: Option<String>,
}

/// Input accepted by the BackEnd's `/v1/tasks` endpoint.
#[derive(Debug, Clone, Deserialize)]
pub(crate) struct Submission {
    pub(crate) task_id: String,
    #[serde(default)]
    pub(crate) root_job_id: String,
    pub(crate) workload: String,
    #[serde(default)]
    pub(crate) required_roles: Vec<String>,
    pub(crate) scene_path: String,
    #[serde(default)]
    pub(crate) output_path: String,
    #[serde(default)]
    pub(crate) seed: String,
    #[serde(default)]
    pub(crate) fragment_count: Option<usize>,
}

/// JSON-compatible task status returned to the BackEnd.
#[derive(Debug, Clone, Serialize)]
pub(crate) struct ControlTask {
    pub(crate) task_id: String,
    pub(crate) root_job_id: String,
    pub(crate) workload: String,
    pub(crate) required_roles: Vec<String>,
    pub(crate) status: String,
    pub(crate) handled_by: String,
    pub(crate) error: String,
    pub(crate) result_hash: String,
    pub(crate) created_unix: i64,
    pub(crate) updated_unix: i64,
    pub(crate) task: serde_json::Value,
}

#[derive(Clone)]
pub(crate) struct ControlRegistry {
    path: PathBuf,
    entries: Arc<Mutex<BTreeMap<String, Entry>>>,
}

impl ControlRegistry {
    /// Opens the durable registry, tolerating a missing or torn last write.
    pub(crate) fn open(path: PathBuf) -> Self {
        let entries = fs::read(&path)
            .ok()
            .and_then(|raw| serde_json::from_slice(&raw).ok())
            .unwrap_or_default();
        Self {
            path,
            entries: Arc::new(Mutex::new(entries)),
        }
    }

    /// Records the request before it is sent to the publisher loop.
    pub(crate) fn register_submission(
        &self,
        root_job_id: String,
        task: NetworkTask,
        required_roles: Vec<String>,
    ) -> Result<(), String> {
        let now = unix_seconds();
        let entry = Entry {
            root_job_id,
            task,
            required_roles,
            created_unix: now,
            updated_unix: now,
            failure: None,
        };
        self.with_entries(|entries| {
            entries.insert(entry.task.task_id.clone(), entry);
        })
    }

    /// Adds a published fragment while retaining the original site id.
    pub(crate) fn register_published(&self, task: &NetworkTask, required_roles: &[String]) {
        let now = unix_seconds();
        let root_job_id = task
            .root_job_id
            .clone()
            .unwrap_or_else(|| task.task_id.clone());
        let _ = self.with_entries(|entries| {
            if let Some(entry) = entries.get_mut(&task.task_id) {
                entry.task = task.clone();
                entry.updated_unix = now;
                return;
            }
            entries.insert(
                task.task_id.clone(),
                Entry {
                    root_job_id,
                    task: task.clone(),
                    required_roles: required_roles.to_vec(),
                    created_unix: now,
                    updated_unix: now,
                    failure: None,
                },
            );
        });
    }

    /// Marks a submitted task that could not be published as failed, with
    /// the reason the BackEnd reports.
    pub(crate) fn mark_failed(&self, task_id: &str, reason: &str) {
        let _ = self.with_entries(|entries| {
            if let Some(entry) = entries.get_mut(task_id) {
                entry.failure = Some(reason.to_string());
                entry.updated_unix = unix_seconds();
            }
        });
    }

    /// Removes a request that could not be queued for publication.
    pub(crate) fn remove_task(&self, task_id: &str) {
        let _ = self.with_entries(|entries| {
            entries.remove(task_id);
        });
    }

    /// Returns all task-book entries belonging to a site workload.
    pub(crate) fn tasks_for_root(
        &self,
        taskbook: &TaskBookState,
        root_job_id: Option<&str>,
    ) -> Vec<ControlTask> {
        let Ok(entries) = self.entries.lock() else {
            return Vec::new();
        };
        entries
            .values()
            .filter(|entry| root_job_id.is_none_or(|root| entry.root_job_id == root))
            .map(|entry| to_control_task(entry, taskbook))
            .collect()
    }

    /// Task ids that can still receive a cancellation event.
    pub(crate) fn cancellable_task_ids(
        &self,
        taskbook: &TaskBookState,
        root_job_id: &str,
    ) -> Vec<String> {
        let Ok(entries) = self.entries.lock() else {
            return Vec::new();
        };
        entries
            .values()
            .filter(|entry| entry.root_job_id == root_job_id)
            .filter(|entry| {
                taskbook
                    .state(&entry.task.task_id)
                    .ok()
                    .flatten()
                    .is_some_and(|state| !state.status.is_terminal())
            })
            .map(|entry| entry.task.task_id.clone())
            .collect()
    }

    fn with_entries(
        &self,
        update: impl FnOnce(&mut BTreeMap<String, Entry>),
    ) -> Result<(), String> {
        let mut entries = self
            .entries
            .lock()
            .map_err(|_| "control registry lock poisoned".to_string())?;
        update(&mut entries);
        let bytes = serde_json::to_vec_pretty(&*entries).map_err(|error| error.to_string())?;
        atomic_write(&self.path, &bytes)
    }
}

fn to_control_task(entry: &Entry, taskbook: &TaskBookState) -> ControlTask {
    let state = taskbook.state(&entry.task.task_id).ok().flatten();
    let (status, handled_by, result_hash, error) = match (&entry.failure, &state) {
        (Some(reason), None) => (
            "failed".to_string(),
            String::new(),
            String::new(),
            reason.clone(),
        ),
        _ => state_summary(state.as_ref()),
    };
    let mut task = serde_json::to_value(&entry.task).unwrap_or_else(|_| serde_json::json!({}));
    if let Some(object) = task.as_object_mut() {
        object.insert(
            "root_job_id".to_string(),
            serde_json::Value::String(entry.root_job_id.clone()),
        );
        object.insert(
            "workload".to_string(),
            serde_json::Value::String(workload_id(&entry.task)),
        );
        object.insert(
            "kind".to_string(),
            serde_json::Value::String("compute".to_string()),
        );
        if let Some(index) = fragment_index(&entry.task.task_id) {
            object.insert("fragment_index".to_string(), serde_json::json!(index));
        }
    }
    ControlTask {
        task_id: entry.task.task_id.clone(),
        root_job_id: entry.root_job_id.clone(),
        workload: workload_id(&entry.task),
        required_roles: entry.required_roles.clone(),
        status,
        handled_by,
        error,
        result_hash,
        created_unix: entry.created_unix,
        updated_unix: state.map(|_| unix_seconds()).unwrap_or(entry.updated_unix),
        task,
    }
}

/// Workload identifier of a task, for the BackEnd.
fn workload_id(task: &NetworkTask) -> String {
    crate::workload::of(task)
        .map_or(crate::workload::DEFAULT_WORKLOAD, |workload| workload.id())
        .to_string()
}

fn state_summary(state: Option<&DerivedTaskState>) -> (String, String, String, String) {
    let Some(state) = state else {
        return (
            "queued".to_string(),
            String::new(),
            String::new(),
            String::new(),
        );
    };
    let handled_by = state.claimant().unwrap_or_default().to_string();
    let result_hash = state
        .finalized_attempt
        .and_then(|attempt| state.attempts.iter().find(|item| item.attempt == attempt))
        .and_then(|attempt| attempt.result.as_ref())
        .map(|result| result.result.sha256.clone())
        .unwrap_or_default();
    match state.status {
        DerivedTaskStatus::Open => (
            "proposed".to_string(),
            handled_by,
            result_hash,
            String::new(),
        ),
        DerivedTaskStatus::Claimed => (
            "running".to_string(),
            handled_by,
            result_hash,
            String::new(),
        ),
        DerivedTaskStatus::LeaseExpired
        | DerivedTaskStatus::Released
        | DerivedTaskStatus::Rejected => (
            "retrying".to_string(),
            handled_by,
            result_hash,
            String::new(),
        ),
        DerivedTaskStatus::Completed => (
            "verifying".to_string(),
            handled_by,
            result_hash,
            String::new(),
        ),
        DerivedTaskStatus::Verified => (
            "verifying".to_string(),
            handled_by,
            result_hash,
            String::new(),
        ),
        DerivedTaskStatus::Finalized => (
            "completed".to_string(),
            handled_by,
            result_hash,
            String::new(),
        ),
        DerivedTaskStatus::Cancelled => (
            "cancelled".to_string(),
            handled_by,
            result_hash,
            "cancelled".to_string(),
        ),
        DerivedTaskStatus::Failed => (
            "failed".to_string(),
            handled_by,
            result_hash,
            "task_failed".to_string(),
        ),
    }
}

fn fragment_index(task_id: &str) -> Option<u32> {
    task_id
        .rsplit_once(".f")
        .and_then(|(_, value)| value.parse::<u32>().ok())
}

fn unix_seconds() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or_default()
}

fn atomic_write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let partial = path.with_extension("partial");
    fs::write(&partial, bytes).map_err(|error| error.to_string())?;
    #[cfg(windows)]
    if path.exists() {
        fs::remove_file(path).map_err(|error| error.to_string())?;
    }
    fs::rename(partial, path).map_err(|error| error.to_string())
}
