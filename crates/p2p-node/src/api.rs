//! Local HTTP API: `POST /publish`, `GET /tasks/{id}`, `GET /health`.
//!
//! Bound to `SILICIUM_API_BIND` (default 127.0.0.1). When
//! `SILICIUM_NODE_CONTROL_TOKEN` is set, every route except `/health` needs
//! `Authorization: Bearer <token>`. Published tasks are sanitized like tasks
//! received from peers (see [`crate::admission`]).

use crate::{admission::SecurityConfig, storage::TaskBookState, task::NetworkTask};
use axum::{
    Router,
    extract::{Json, Path as AxumPath, Request, State},
    http::{StatusCode, header},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use silicium_node_core::p2p::TaskEnvelope;
use std::sync::Arc;
use tokio::sync::mpsc;

#[derive(Clone)]
pub(crate) struct ApiState {
    pub(crate) tx_publish: mpsc::Sender<NetworkTask>,
    pub(crate) taskbook: TaskBookState,
    pub(crate) security: Arc<SecurityConfig>,
}

/// Builds the API router.
pub(crate) fn router(state: ApiState) -> Router {
    Router::new()
        .route("/publish", post(publish_task))
        .route("/tasks/{task_id}", get(task_status))
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

async fn health() -> impl IntoResponse {
    (
        StatusCode::OK,
        Json(serde_json::json!({"status": "ok", "service": "p2p_node"})),
    )
}
