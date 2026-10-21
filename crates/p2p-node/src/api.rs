//! Local HTTP API: `POST /publish`, `GET /tasks/{id}`, `GET /jobs/{id}`,
//! `GET /health`.
//!
//! Bound to `SILICIUM_API_BIND` (default 127.0.0.1). When
//! `SILICIUM_NODE_CONTROL_TOKEN` is set, every route except `/health` needs
//! `Authorization: Bearer <token>`. Published tasks are sanitized like tasks
//! received from peers (see [`crate::admission`]).

use crate::{
    admission::SecurityConfig,
    content::ContentStore,
    control::{ControlRegistry, ControlTask, Submission},
    jobs::result_file,
    jobs::{FRAGMENT_SUFFIX_EXAMPLE, JobStore, MAX_FRAGMENTS_LIMIT},
    publishing::{ImportError, import_input},
    storage::TaskBookState,
    task::{NetworkTask, PeerProfile, utc_now as task_utc_now},
    workload::embedding::search::{SearchRequest, search},
};
use axum::{
    Router,
    extract::{Json, Path as AxumPath, Query, Request, State},
    http::{StatusCode, header},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use serde::{Deserialize, Serialize};
use silicium_node_core::{p2p::TaskEnvelope, taskbook::TaskEvent};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::PathBuf,
    sync::{Arc, Mutex},
};
use tokio::sync::mpsc;

const PEER_STALE_AFTER_SECONDS: i64 = 15;

#[derive(Clone)]
pub(crate) struct ApiState {
    pub(crate) tx_publish: mpsc::Sender<NetworkTask>,
    pub(crate) tx_events: mpsc::Sender<silicium_node_core::taskbook::TaskEvent>,
    pub(crate) taskbook: TaskBookState,
    pub(crate) jobs: JobStore,
    pub(crate) content: ContentStore,
    pub(crate) control: ControlRegistry,
    pub(crate) local_peer_id: String,
    pub(crate) peers: Arc<Mutex<BTreeSet<String>>>,
    pub(crate) peer_profiles: Arc<Mutex<BTreeMap<String, PeerProfile>>>,
    pub(crate) security: Arc<SecurityConfig>,
    /// Data directory of the node (models used by the search).
    pub(crate) data_dir: PathBuf,
}

/// Builds the API router.
pub(crate) fn router(state: ApiState) -> Router {
    Router::new()
        .route("/publish", post(publish_task))
        .route("/tasks/{task_id}", get(task_status))
        .route("/jobs/{job_id}", get(job_status))
        .route(
            "/v1/tasks",
            get(list_control_tasks).post(submit_control_task),
        )
        .route(
            "/v1/workloads/{root_job_id}/cancel",
            post(cancel_control_workload),
        )
        .route("/v1/peers", get(control_peers))
        .route("/v1/embedding/search", post(embedding_search))
        .route_layer(middleware::from_fn_with_state(state.clone(), require_token))
        .route("/health", get(health))
        .route("/healthz", get(health))
        .with_state(state)
}

async fn require_token(State(state): State<ApiState>, request: Request, next: Next) -> Response {
    if let Some(token) = &state.security.control_token {
        let expected = format!("Bearer {token}");
        let given = request
            .headers()
            .get(header::AUTHORIZATION)
            .and_then(|value| value.to_str().ok());
        if given != Some(expected.as_str()) {
            return (StatusCode::UNAUTHORIZED, "Unauthorized").into_response();
        }
    }
    next.run(request).await
}

async fn publish_task(
    State(state): State<ApiState>,
    Json(task): Json<NetworkTask>,
) -> impl IntoResponse {
    // Task book identifiers start with the publisher's key (nobody else can
    // propose them); a plain name is prefixed with this node's key.
    let mut task = task;
    task.task_id = state.taskbook.owned_task_id(&task.task_id);
    // Room is kept for the fragment suffix (`.f000`).
    if !TaskEvent::is_valid_task_id(&format!("{}{FRAGMENT_SUFFIX_EXAMPLE}", task.task_id)) {
        return (
            StatusCode::BAD_REQUEST,
            "invalid task id: up to 90 characters among A-Z a-z 0-9 . _ -",
        )
            .into_response();
    }
    let task = match state.security.admit_local(TaskEnvelope::from(task)) {
        Ok(task) => task,
        Err(reason) => return (StatusCode::BAD_REQUEST, reason).into_response(),
    };
    match state.tx_publish.send(task).await {
        Ok(_) => (StatusCode::OK, "Task queued for publish").into_response(),
        Err(_) => (StatusCode::INTERNAL_SERVER_ERROR, "Channel closed").into_response(),
    }
}

#[derive(Debug, Deserialize)]
struct ControlTaskQuery {
    root_job_id: Option<String>,
}

#[derive(Debug, Serialize)]
struct ControlTaskList {
    tasks: Vec<ControlTask>,
}

/// Accepts the stable BackEnd submission contract and imports its scene by
/// hash before the task is handed to the publisher loop.
async fn submit_control_task(
    State(state): State<ApiState>,
    Json(submission): Json<Submission>,
) -> impl IntoResponse {
    let Some(workload) = crate::workload::find(&submission.workload) else {
        let message = format!(
            "unsupported workload (known: {})",
            crate::workload::known_ids()
        );
        return api_error(StatusCode::BAD_REQUEST, &message);
    };
    let task_id = submission.task_id.trim();
    let root_job_id = if submission.root_job_id.trim().is_empty() {
        task_id
    } else {
        submission.root_job_id.trim()
    };
    if task_id.is_empty() || root_job_id.is_empty() {
        return api_error(StatusCode::BAD_REQUEST, "task_id is required");
    }
    let owned_task_id = state.taskbook.owned_task_id(task_id);
    if !TaskEvent::is_valid_task_id(&format!("{}{FRAGMENT_SUFFIX_EXAMPLE}", owned_task_id)) {
        return api_error(StatusCode::BAD_REQUEST, "invalid task id");
    }
    let requested_fragment_count = match submission.fragment_count {
        Some(count) if (1..=MAX_FRAGMENTS_LIMIT).contains(&count) => Some(count),
        Some(_) => {
            return api_error(
                StatusCode::BAD_REQUEST,
                "fragment_count must be between 1 and 256",
            );
        }
        None => None,
    };

    let source = PathBuf::from(submission.scene_path.trim());
    // The node deliberately chooses a relative per-task output path during
    // admission; the requested site path is represented by the compatibility
    // projection after the fragments are reassembled.
    let _requested_output_path = submission.output_path.trim();
    let source = if source.is_absolute() {
        source
    } else {
        state.content.absolute(source.to_string_lossy().as_ref())
    };
    // A workload may turn the submitted file into its shared input (the
    // corpus of a document search); its refusal is a message for the user.
    let (scene_path, scene_sha256) = match import_input(&state.content, workload, &source).await {
        Ok(hash) => (ContentStore::relative_path(&hash), Some(hash)),
        Err(ImportError::Rejected(message)) => {
            return api_error(StatusCode::BAD_REQUEST, &message);
        }
        Err(ImportError::Storage(message)) => {
            println!(" Input of {task_id} not stored: {message}");
            return api_error(StatusCode::INTERNAL_SERVER_ERROR, "input_not_stored");
        }
    };
    let envelope = silicium_node_core::p2p::TaskEnvelope {
        task_id: owned_task_id.clone(),
        scene_path,
        output_path: String::new(),
        seed: if submission.seed.trim().is_empty() {
            task_id.to_string()
        } else {
            submission.seed
        },
        hardware_hint: None,
        runtime_hint: None,
        runtime_args: Vec::new(),
        runtime_env: Default::default(),
        runtime_workdir: None,
        runtime_module_path: None,
        runtime_image: None,
        scene_sha256,
        region: None,
        workload: Some(workload.id().to_string()),
        byte_range: None,
    };
    let Ok(mut task) = state.security.admit_local(envelope) else {
        return api_error(StatusCode::BAD_REQUEST, "invalid task envelope");
    };
    task.root_job_id = Some(root_job_id.to_string());
    task.requested_fragment_count = requested_fragment_count;
    let required_roles = if submission.required_roles.is_empty() {
        vec!["compute".to_string(), "verify".to_string()]
    } else {
        submission.required_roles
    };
    if let Err(error) =
        state
            .control
            .register_submission(root_job_id.to_string(), task.clone(), required_roles)
    {
        return api_error(StatusCode::INTERNAL_SERVER_ERROR, &error);
    }
    if state.tx_publish.send(task.clone()).await.is_err() {
        state.control.remove_task(&task.task_id);
        return api_error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "publisher channel closed",
        );
    }
    let response = state
        .control
        .tasks_for_root(&state.taskbook, Some(root_job_id))
        .into_iter()
        .find(|item| item.task_id == task.task_id)
        .unwrap_or_else(|| ControlTask {
            task_id: task.task_id,
            root_job_id: root_job_id.to_string(),
            workload: workload.id().to_string(),
            required_roles: vec!["compute".to_string(), "verify".to_string()],
            status: "queued".to_string(),
            handled_by: String::new(),
            error: String::new(),
            result_hash: String::new(),
            created_unix: 0,
            updated_unix: 0,
            task: serde_json::json!({"root_job_id": root_job_id, "workload": workload.id(), "kind": "compute"}),
            trace: None,
        });
    (StatusCode::ACCEPTED, Json(response)).into_response()
}

async fn list_control_tasks(
    Query(query): Query<ControlTaskQuery>,
    State(state): State<ApiState>,
) -> impl IntoResponse {
    let root_job_id = query
        .root_job_id
        .as_deref()
        .map(str::trim)
        .filter(|id| !id.is_empty());
    (
        StatusCode::OK,
        Json(ControlTaskList {
            tasks: state.control.tasks_for_root(&state.taskbook, root_job_id),
        }),
    )
        .into_response()
}

async fn cancel_control_workload(
    AxumPath(root_job_id): AxumPath<String>,
    State(state): State<ApiState>,
) -> impl IntoResponse {
    let task_ids = state
        .control
        .cancellable_task_ids(&state.taskbook, root_job_id.trim());
    let mut cancelled = 0;
    for task_id in task_ids {
        match state.taskbook.append_signed(
            &task_id,
            silicium_node_core::taskbook::TaskEventBody::TaskCancelled,
        ) {
            Ok(event) => {
                cancelled += 1;
                let _ = state.tx_events.send(event).await;
            }
            Err(error) => eprintln!("cancel {task_id} failed: {error}"),
        }
    }
    (
        StatusCode::OK,
        Json(serde_json::json!({"cancelled": cancelled})),
    )
        .into_response()
}

async fn control_peers(State(state): State<ApiState>) -> impl IntoResponse {
    let now = unix_seconds();
    let connected = state
        .peers
        .lock()
        .map(|items| items.clone())
        .unwrap_or_default();
    let profiles = state
        .peer_profiles
        .lock()
        .map(|items| items.clone())
        .unwrap_or_default();
    let mut peers = Vec::new();
    let mut represented = BTreeSet::new();
    for profile in profiles.values() {
        let is_self = profile.peer_id == state.local_peer_id;
        let online = is_self
            || (connected.contains(&profile.peer_id)
                && now.saturating_sub(profile.last_seen_unix) <= PEER_STALE_AFTER_SECONDS);
        let telemetry = profile
            .activity
            .get("telemetry")
            .cloned()
            .unwrap_or(serde_json::Value::Null);
        peers.push(serde_json::json!({
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
        }));
        represented.insert(profile.peer_id.clone());
    }
    for peer_id in connected
        .iter()
        .filter(|peer_id| !represented.contains(*peer_id))
    {
        peers.push(serde_json::json!({
            "node_id": peer_id,
            "peer_id": peer_id,
            "self": peer_id == &state.local_peer_id,
            "online": true,
            "status": "connected",
            "last_seen_unix": now,
            "last_seen_utc": task_utc_now(),
            "roles": roles(),
        }));
    }
    let tasks = state.control.tasks_for_root(&state.taskbook, None);
    let peer_count = peers
        .iter()
        .filter(|peer| peer["online"].as_bool().unwrap_or(false))
        .count();
    let queue_depth = tasks
        .iter()
        .filter(|task| matches!(task.status.as_str(), "queued" | "proposed"))
        .count();
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "peers": peers,
            "metrics": {
                "online_peers": peer_count,
                "known_tasks": tasks.len(),
                "queue_depth": queue_depth,
                "active_tasks": tasks.iter().filter(|task| !matches!(task.status.as_str(), "completed" | "failed" | "cancelled")).count(),
                "updated_utc": utc_now(),
            }
        })),
    )
        .into_response()
}

fn api_error(status: StatusCode, message: &str) -> Response {
    (status, Json(serde_json::json!({"error": message}))).into_response()
}

fn roles() -> Vec<String> {
    std::env::var("SILICIUM_NODE_ROLES")
        .unwrap_or_else(|_| "compute,verify".to_string())
        .split(',')
        .map(str::trim)
        .filter(|role| !role.is_empty())
        .map(str::to_string)
        .collect()
}

fn unix_seconds() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or_default()
}

fn utc_now() -> String {
    format!("{}", unix_seconds())
}

async fn task_status(
    AxumPath(task_id): AxumPath<String>,
    State(state): State<ApiState>,
) -> impl IntoResponse {
    match state.taskbook.state(&task_id) {
        Ok(Some(task)) => (StatusCode::OK, Json(task)).into_response(),
        Ok(None) => (StatusCode::NOT_FOUND, "Task not found").into_response(),
        Err(err) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            format!("Task book unavailable: {err}"),
        )
            .into_response(),
    }
}

/// A job of this node: its manifest, the status of each fragment, and the
/// paths (relative to the work directory) of the results collected so far
/// and of the job result once assembled (`outputs`; for the raytracer also
/// `image` and `png`).
async fn job_status(
    AxumPath(job_id): AxumPath<String>,
    State(state): State<ApiState>,
) -> impl IntoResponse {
    let Some(job) = state.jobs.manifest(&job_id) else {
        return (StatusCode::NOT_FOUND, "Job not found").into_response();
    };
    let collected = state.jobs.collected(&job);
    let fragments: Vec<_> = job
        .fragments
        .iter()
        .map(|fragment| {
            let status = state
                .taskbook
                .state(&fragment.task_id)
                .ok()
                .flatten()
                .map(|task| task.status);
            serde_json::json!({
                "task_id": fragment.task_id,
                "region": fragment.region,
                "byte_range": fragment.byte_range,
                "status": status,
                "image": collected
                    .contains(&fragment.task_id)
                    .then(|| JobStore::fragment_result_path(&job, &fragment.task_id)),
            })
        })
        .collect();
    let complete = state.jobs.is_assembled(&job.job_id);
    let output = |extension: &str| complete.then(|| result_file(&job.job_id, extension));
    let outputs: Vec<String> = crate::workload::find(&job.workload)
        .map(|workload| workload.published_outputs())
        .unwrap_or_default()
        .iter()
        .filter_map(|item| output(item.extension))
        .collect();
    let body = serde_json::json!({
        "job_id": job.job_id,
        "workload": job.workload,
        "width": job.width,
        "height": job.height,
        "input_bytes": job.input_bytes,
        "fragments_total": job.fragments.len(),
        "fragments_collected": collected.len(),
        "fragments": fragments,
        "outputs": outputs,
        "image": outputs.first(),
        "png": outputs.iter().find(|path| path.ends_with(".png")),
    });
    (StatusCode::OK, Json(body)).into_response()
}

/// `POST /v1/embedding/search`: the best passages of document-search jobs
/// for a query (see [`crate::workload::embedding::search`]).
async fn embedding_search(
    State(state): State<ApiState>,
    Json(request): Json<SearchRequest>,
) -> Response {
    match search(&state.jobs, &state.data_dir, request).await {
        Ok(response) => (StatusCode::OK, Json(response)).into_response(),
        Err(error) => error.into_response(),
    }
}

async fn health() -> impl IntoResponse {
    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "ok", "ok": true, "service": "p2p_node"})),
    )
}
