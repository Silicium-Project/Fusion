//! BackEnd-compatible files written by the Rust node.
//!
//! The files are intentionally projections of the task book and job store.
//! They are written atomically so the existing Go handlers can keep reading
//! progress, summaries, previews and node telemetry during the dev rollout.

use crate::{
    control::{ControlRegistry, ControlTask},
    jobs::{JobManifest, JobStore, result_file},
    peers::profile_is_worker,
    storage::TaskBookState,
    task::PeerProfile,
    workload::{self, Workload},
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Clone)]
pub(crate) struct CompatibilityWriter {
    export_dir: PathBuf,
    storage_dir: PathBuf,
    node_id: String,
    roles: Vec<String>,
    app_version: String,
    release_channel: String,
    release_build: String,
}

impl CompatibilityWriter {
    /// Creates a writer using the same paths as the BackEnd environment.
    pub(crate) fn new(peer_id: &str) -> Self {
        let compute_root = env::var("SILICIUM_COMPUTE_ROOT")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("work"));
        let export_dir = env_value("SILICIUM_EXPORT_DIR")
            .or_else(|| env_value("SILICIUM_ORCHESTRATOR_EXPORT_DIR"))
            .unwrap_or_else(|| compute_root.join("export").display().to_string());
        let storage_dir = env_value("SILICIUM_WORKLOAD_STORAGE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| compute_root.clone());
        Self {
            export_dir: PathBuf::from(export_dir),
            storage_dir,
            node_id: env_value("SILICIUM_NODE_ID")
                .or_else(|| env_value("SILICIUM_ORCHESTRATOR_NODE_ID"))
                .unwrap_or_else(|| peer_id.to_string()),
            roles: roles(),
            app_version: env_value("SILICIUM_APP_VERSION").unwrap_or_else(|| "unknown".to_string()),
            release_channel: env_value("SILICIUM_RELEASE_CHANNEL")
                .unwrap_or_else(|| "dev".to_string()),
            release_build: env_value("SILICIUM_RELEASE_BUILD")
                .unwrap_or_else(|| "local".to_string()),
        }
    }

    /// Writes all compatibility projections for the current node state.
    pub(crate) fn refresh(
        &self,
        control: &ControlRegistry,
        taskbook: &TaskBookState,
        jobs: &JobStore,
        peers: &BTreeSet<String>,
        profiles: &BTreeMap<String, PeerProfile>,
    ) {
        self.write_peer_files(control, taskbook, peers, profiles);
        self.write_job_files(control, taskbook, jobs);
    }

    fn write_peer_files(
        &self,
        control: &ControlRegistry,
        taskbook: &TaskBookState,
        peers: &BTreeSet<String>,
        profiles: &BTreeMap<String, PeerProfile>,
    ) {
        let now = unix_seconds();
        let mut represented = BTreeSet::new();
        let mut peer_rows: Vec<Value> = profiles
            .values()
            .map(|profile| {
                represented.insert(profile.peer_id.clone());
                let is_self = profile.node_id == self.node_id;
                let online = is_self || peers.contains(&profile.peer_id);
                let telemetry = profile
                    .activity
                    .get("telemetry")
                    .cloned()
                    .unwrap_or(Value::Null);
                json!({
                    "node_id": profile.node_id,
                    "peer_id": profile.peer_id,
                    "self": is_self,
                    "online": online,
                    "status": if online { "connected" } else { "disconnected" },
                    "last_seen_unix": profile.last_seen_unix,
                    "last_seen_utc": profile.last_seen_utc,
                    "roles": profile.roles,
                    "app_version": profile.app_version,
                    "release_channel": profile.release_channel,
                    "release_build": profile.release_build,
                    "capacity": profile.capacity,
                    "activity": profile.activity,
                    "task_queue": profile.task_queue,
                    "telemetry": telemetry,
                    // Desktop app fields: a connected worker listens for
                    // tasks continuously (no polling as in the Python node).
                    "updated_utc": profile.last_seen_utc,
                    "last_claim_poll_unix": if profile_is_worker(profile) { profile.last_seen_unix } else { 0 },
                })
            })
            .collect();
        peer_rows.extend(
            peers
                .iter()
                .filter(|peer| !represented.contains(*peer))
                .map(|peer| {
                    json!({
                        "node_id": peer,
                        "peer_id": peer,
                        "self": peer == &self.node_id,
                        "online": true,
                        "status": "connected",
                        "last_seen_unix": now,
                        "last_seen_utc": utc_now(),
                        "roles": self.roles.clone(),
                        "app_version": self.app_version.clone(),
                        "release_channel": self.release_channel.clone(),
                        "release_build": self.release_build.clone(),
                    })
                }),
        );
        let tasks = control.tasks_for_root(taskbook, None);
        let active = tasks.iter().filter(|task| is_active(&task.status)).count();
        let metrics = json!({
            "online_peers": peer_rows.len(),
            "known_tasks": tasks.len(),
            "active_tasks": active,
            "queue_depth": tasks.iter().filter(|task| task.status == "queued").count(),
            "updated_utc": utc_now(),
        });
        let payload = json!({"schema_version": 1, "node_id": self.node_id.clone(), "peers": peer_rows, "metrics": metrics});
        write_json(
            &self
                .export_dir
                .join(format!("node.{}.peers.json", path_id(&self.node_id))),
            &payload,
        );

        let queue: Vec<Value> = tasks
            .iter()
            .filter(|task| is_active(&task.status))
            .map(|task| {
                json!({
                    "task_id": task.task_id,
                    "root_job_id": task.root_job_id,
                    "status": task.status,
                    "handled_by": task.handled_by,
                    "workload": task.workload,
                })
            })
            .collect();
        // This node's latest resource sample, from its own heartbeat profile.
        let telemetry = profiles
            .values()
            .find(|profile| profile.node_id == self.node_id)
            .and_then(|profile| profile.activity.get("telemetry").cloned())
            .unwrap_or_else(|| json!({"updated_utc": utc_now()}));
        let heartbeat = json!({
            "schema_version": 1,
            "node_id": self.node_id.clone(),
            "roles": self.roles.clone(),
            "app_version": self.app_version.clone(),
            "release_channel": self.release_channel.clone(),
            "release_build": self.release_build.clone(),
            "capacity": {"logical_cpu_count": telemetry["logical_cpu_count"]},
            "activity": {"active_tasks": queue, "telemetry": telemetry},
            "task_queue": queue,
            "telemetry": telemetry,
            "updated_utc": utc_now(),
        });
        write_json(
            &self
                .export_dir
                .join(format!("node.{}.heartbeat.json", path_id(&self.node_id))),
            &heartbeat,
        );
        write_json(
            &self
                .export_dir
                .join(format!("node.{}.metrics.json", path_id(&self.node_id))),
            &json!({
                "handled": tasks.iter().filter(|task| task.status == "completed").count(),
                "failed": tasks.iter().filter(|task| task.status == "failed").count(),
                "retried": tasks.iter().filter(|task| task.status == "retrying").count(),
                "updated_utc": utc_now(),
                "runtime": telemetry,
            }),
        );
    }

    fn write_job_files(
        &self,
        control: &ControlRegistry,
        taskbook: &TaskBookState,
        jobs: &JobStore,
    ) {
        let tasks = control.tasks_for_root(taskbook, None);
        let mut grouped: BTreeMap<String, Vec<ControlTask>> = BTreeMap::new();
        for task in tasks {
            grouped
                .entry(task.root_job_id.clone())
                .or_default()
                .push(task);
        }
        for (root_id, tasks) in grouped {
            self.write_one_job(&root_id, &tasks, jobs);
        }
    }

    fn write_one_job(&self, root_id: &str, tasks: &[ControlTask], jobs: &JobStore) {
        let manifest = jobs.manifest_for_root(root_id);
        let workload_id = manifest
            .as_ref()
            .map(|job| job.workload.clone())
            .or_else(|| tasks.first().map(|task| task.workload.clone()))
            .unwrap_or_default();
        let Some(workload) = workload::find(&workload_id) else {
            return;
        };
        let fragment_count = manifest
            .as_ref()
            .map(|job| job.fragments.len())
            .unwrap_or(tasks.len());
        let job_dir = self
            .storage_dir
            .join(workload.storage_dir())
            .join(path_id(root_id));
        let fragments = manifest
            .as_ref()
            .map(|job| self.fragment_rows(job, tasks, jobs, &job_dir))
            .unwrap_or_else(|| self.single_fragment_rows(tasks, jobs, workload));
        let completed = fragments
            .iter()
            .filter(|fragment| fragment["status"] == "completed")
            .count();
        let failed = fragments
            .iter()
            .filter(|fragment| fragment["status"] == "failed")
            .count();
        let complete = manifest
            .as_ref()
            .is_some_and(|job| jobs.is_assembled(&job.job_id));
        let progress = if fragment_count == 0 {
            0.0
        } else {
            completed as f64 * 100.0 / fragment_count as f64
        };
        let stage = if complete {
            "completed"
        } else if failed > 0 {
            "failed"
        } else if completed > 0 {
            "computing"
        } else {
            "queued"
        };
        let progress_payload = json!({
            "schema_version": 1,
            "job_id": root_id,
            "stage": stage,
            "progress": progress,
            "fragment_count": fragment_count,
            "fragments": fragments,
            "updated_utc": utc_now(),
            "success": if complete { Value::Bool(true) } else if failed > 0 { Value::Bool(false) } else { Value::Null },
        });
        write_json(&job_dir.join("raytracer-progress.json"), &progress_payload);

        let mut summary = json!({
            "schema_version": 1,
            "job_id": root_id,
            "workload": workload.id(),
            "fragment_count": fragment_count,
            "fragments": progress_payload["fragments"],
            "updated_utc": utc_now(),
            "billing": billing(tasks),
        });
        if complete {
            if let Some(job) = manifest {
                let mut copied_all = true;
                for output in workload.published_outputs() {
                    let copied = self.copy_final(
                        jobs.root().join(result_file(&job.job_id, output.extension)),
                        &job_dir.join(output.target),
                    );
                    match copied {
                        Some(path) => {
                            for key in output.summary_keys {
                                summary[*key] = Value::String(path.display().to_string());
                            }
                        }
                        None => copied_all = false,
                    }
                }
                summary["success"] = Value::Bool(copied_all);
            }
        } else if failed > 0 {
            summary["success"] = Value::Bool(false);
            summary["failure_detail"] = Value::String("rust_node_fragment_failed".to_string());
            summary["error"] = Value::String("rust_node_fragment_failed".to_string());
        }
        write_json(&job_dir.join("raytracer-summary.json"), &summary);
    }

    fn fragment_rows(
        &self,
        job: &JobManifest,
        tasks: &[ControlTask],
        jobs: &JobStore,
        job_dir: &Path,
    ) -> Vec<Value> {
        let by_id: BTreeMap<&str, &ControlTask> = tasks
            .iter()
            .map(|task| (task.task_id.as_str(), task))
            .collect();
        job.fragments
            .iter()
            .enumerate()
            .map(|(index, fragment)| {
                let task = by_id.get(fragment.task_id.as_str());
                let status = task.map(|item| item.status.as_str()).unwrap_or("queued");
                let source = jobs
                    .root()
                    .join(JobStore::fragment_result_path(job, &fragment.task_id));
                if source.is_file() && job.workload == workload::raytracer::ID {
                    self.write_fragment_preview(index, &source, job_dir);
                }
                json!({
                    "fragment_index": index,
                    "fragment_count": job.fragments.len(),
                    "task_id": fragment.task_id,
                    "status": status,
                    "region": fragment.region,
                    "byte_range": fragment.byte_range,
                    "items": fragment.items.map(|items| items.count),
                    "result_path": source.display().to_string(),
                    "receipt_attestation": {"accepted": status == "completed"},
                    "compute_billable_work_units": 0,
                    "verify_billable_work_units": 0,
                    "compute_receipt_hash": task.map(|item| item.result_hash.clone()).unwrap_or_default(),
                    "verify_receipt_hash": task.map(|item| item.result_hash.clone()).unwrap_or_default(),
                })
            })
            .collect()
    }

    fn single_fragment_rows(
        &self,
        tasks: &[ControlTask],
        jobs: &JobStore,
        workload: &dyn Workload,
    ) -> Vec<Value> {
        tasks
            .iter()
            .enumerate()
            .map(|(index, task)| {
                json!({
                    "fragment_index": index,
                    "fragment_count": tasks.len(),
                    "task_id": task.task_id,
                    "status": task.status,
                    "receipt_attestation": {"accepted": task.status == "completed"},
                    "compute_billable_work_units": 0,
                    "verify_billable_work_units": 0,
                    "compute_receipt_hash": task.result_hash,
                    "verify_receipt_hash": task.result_hash,
                    "result_path": jobs
                        .root()
                        .join(result_file(&task.task_id, workload.fragment_extension()))
                        .display()
                        .to_string(),
                })
            })
            .collect()
    }

    fn write_fragment_preview(&self, index: usize, source: &Path, job_dir: &Path) {
        let Ok(bytes) = fs::read(source) else { return };
        let Ok(image) = silicium_raytracer::pipeline::ppm::parse(&bytes, "fragment") else {
            return;
        };
        let Ok(png) =
            silicium_raytracer::pipeline::png::encode_rgb(image.width, image.height, &image.pixels)
        else {
            return;
        };
        write_bytes(
            &job_dir
                .join("fragments")
                .join(format!("fragment-{index:03}.png")),
            &png,
        );
    }

    /// Copies a final result file for the BackEnd. Result files never change
    /// once written: a copy of the same size is already there and is not
    /// rewritten on every refresh (indexes weigh hundreds of megabytes).
    fn copy_final(&self, source: PathBuf, target: &Path) -> Option<PathBuf> {
        let source_size = fs::metadata(&source).ok()?.len();
        if fs::metadata(target).is_ok_and(|meta| meta.is_file() && meta.len() == source_size) {
            return Some(target.to_path_buf());
        }
        let bytes = fs::read(source).ok()?;
        write_bytes(target, &bytes);
        target.is_file().then(|| target.to_path_buf())
    }
}

fn billing(tasks: &[ControlTask]) -> Value {
    let hashes: Vec<&str> = tasks
        .iter()
        .filter(|task| task.status == "completed")
        .map(|task| task.result_hash.as_str())
        .filter(|hash| !hash.is_empty())
        .collect();
    let mut digest = Sha256::new();
    for hash in &hashes {
        digest.update(hash.as_bytes());
        digest.update(b"\n");
    }
    json!({"billable_work_units": 0, "receipt_set_hash": format_digest(digest.finalize())})
}

fn format_digest(bytes: impl AsRef<[u8]>) -> String {
    bytes
        .as_ref()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn write_json(path: &Path, payload: &Value) {
    if let Ok(bytes) = serde_json::to_vec_pretty(payload) {
        write_bytes(path, &bytes);
    }
}

fn write_bytes(path: &Path, bytes: &[u8]) {
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let partial = path.with_extension("partial");
    if fs::write(&partial, bytes).is_ok() {
        let _ = fs::rename(partial, path);
    }
}

fn is_active(status: &str) -> bool {
    !matches!(status, "completed" | "failed" | "cancelled")
}

fn path_id(value: &str) -> String {
    value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.') {
                character
            } else {
                '_'
            }
        })
        .collect()
}

fn roles() -> Vec<String> {
    env_value("SILICIUM_NODE_ROLES")
        .unwrap_or_else(|| "compute,verify".to_string())
        .split(',')
        .map(str::trim)
        .filter(|role| !role.is_empty())
        .map(str::to_string)
        .collect()
}

fn env_value(key: &str) -> Option<String> {
    env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn unix_seconds() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or_default()
}

fn utc_now() -> String {
    let seconds = unix_seconds();
    let days = seconds.div_euclid(86_400);
    let day_seconds = seconds.rem_euclid(86_400);
    let hour = day_seconds / 3_600;
    let minute = (day_seconds % 3_600) / 60;
    let second = day_seconds % 60;
    let (year, month, day) = civil_date(days);
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z")
}

// Howard Hinnant's proleptic-Gregorian civil-from-days conversion, kept here
// to avoid making the small runtime depend on a second date crate.
fn civil_date(days_since_unix_epoch: i64) -> (i64, i64, i64) {
    let z = days_since_unix_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 }.div_euclid(146_097);
    let day_of_era = z - era * 146_097;
    let year_of_era = (day_of_era - day_of_era / 1_460 + day_of_era / 36_524
        - day_of_era / 146_096)
        .div_euclid(365);
    let year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_part = (5 * day_of_year + 2).div_euclid(153);
    let day = day_of_year - (153 * month_part + 2).div_euclid(5) + 1;
    let month = month_part + if month_part < 10 { 3 } else { -9 };
    (year + i64::from(month <= 2), month, day)
}
