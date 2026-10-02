//! Local HTTP API: `POST /publish`, `GET /tasks/{id}`, `GET /jobs/{id}`,
//! `GET /health`.
//!
//! Bound to `SILICIUM_API_BIND` (default 127.0.0.1). When
//! `SILICIUM_NODE_CONTROL_TOKEN` is set, every route except `/health` needs
//! `Authorization: Bearer <token>`. Published tasks are sanitized like tasks
//! received from peers (see [`crate::admission`]).

use crate::{
    admission::SecurityConfig,
    jobs::{FRAGMENT_SUFFIX_EXAMPLE, JobStore},
    results::result_path,
    storage::TaskBookState,
    task::NetworkTask,
};
use axum::{
    Router,
    extract::{Json, Path as AxumPath, Request, State},
    http::{StatusCode, header},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use silicium_node_core::{p2p::TaskEnvelope, taskbook::TaskEvent};
use std::sync::Arc;
use tokio::sync::mpsc;

#[derive(Clone)]
pub(crate) struct ApiState {
    pub(crate) tx_publish: mpsc::Sender<NetworkTask>,
    pub(crate) taskbook: TaskBookState,
    pub(crate) jobs: JobStore,
    pub(crate) security: Arc<SecurityConfig>,
}

/// Builds the API router.
pub(crate) fn router(state: ApiState) -> Router {
    Router::new()
        .route("/publish", post(publish_task))
        .route("/tasks/{task_id}", get(task_status))
        .route("/jobs/{job_id}", get(job_status))
        .route_layer(middleware::from_fn_with_state(state.clone(), require_token))
        .route("/health", get(health))
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
/// paths (relative to the work directory) of the images collected so far.
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
                "status": status,
                "image": collected
                    .contains(&fragment.task_id)
                    .then(|| result_path(&fragment.task_id)),
            })
        })
        .collect();
    let complete = state.jobs.is_assembled(&job.job_id);
    let body = serde_json::json!({
        "job_id": job.job_id,
        "width": job.width,
        "height": job.height,
        "fragments_total": job.fragments.len(),
        "fragments_collected": collected.len(),
        "fragments": fragments,
        "image": complete.then(|| result_path(&job.job_id)),
        "png": complete.then(|| JobStore::png_path(&job.job_id)),
    });
    (StatusCode::OK, Json(body)).into_response()
}

async fn health() -> impl IntoResponse {
    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "ok", "service": "p2p_node"})),
    )
}
