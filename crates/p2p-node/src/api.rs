//! Local HTTP API (bound to 127.0.0.1): `POST /publish`, `GET /tasks/{id}`,
//! `GET /health`.

use crate::{storage::TaskBookState, task::NetworkTask};
use axum::{
    Router,
    extract::{Json, Path as AxumPath, State},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
};
use tokio::sync::mpsc;

#[derive(Clone)]
pub(crate) struct ApiState {
    pub(crate) tx_publish: mpsc::Sender<NetworkTask>,
    pub(crate) taskbook: TaskBookState,
}

/// Builds the API router.
pub(crate) fn router(state: ApiState) -> Router {
    Router::new()
        .route("/publish", post(publish_task))
        .route("/tasks/{task_id}", get(task_status))
        .route("/health", get(health))
        .with_state(state)
}

async fn publish_task(
    State(state): State<ApiState>,
    Json(task): Json<NetworkTask>,
) -> impl IntoResponse {
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
