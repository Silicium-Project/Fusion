//! `reputation_bridge`: HTTP service holding peer reputation scores and checking
//! Solana stakes. Configuration and API: `crates/reputation-bridge/README.md`.

mod reputation;
mod solana_bridge;

use axum::{
    extract::{Json, State},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Router,
};
use reputation::{new_shared_store, SharedReputationStore};
use serde::Deserialize;
use solana_bridge::{SolanaManager, StakeQuery, StakeResponse};
use std::{env, sync::Arc};
use tokio::net::TcpListener;

// ── Shared Application State ────────────────────────────────────────────────

#[derive(Clone)]
struct AppState {
    reputation: SharedReputationStore,
    solana: Arc<SolanaManager>,
}

// ── Reputation Endpoints ─────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct ObserveRequest {
    peer_id: String,
    success: bool,
    weight: f64,
}

async fn get_score(
    State(state): State<AppState>,
    Json(body): Json<serde_json::Value>,
) -> impl IntoResponse {
    let peer_id = match body.get("peer_id").and_then(|v| v.as_str()) {
        Some(id) => id.to_string(),
        None => {
            return (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": "peer_id required"}))).into_response();
        }
    };

    let score = {
        let store = state.reputation.read().unwrap();
        store.get_score(&peer_id)
    };

    (StatusCode::OK, Json(serde_json::json!({ "peer_id": peer_id, "score": score }))).into_response()
}

async fn observe_peer(
    State(state): State<AppState>,
    Json(body): Json<ObserveRequest>,
) -> impl IntoResponse {
    {
        let mut store = state.reputation.write().unwrap();
        store.observe_peer(&body.peer_id, body.success, body.weight);
    }

    let score = {
        let store = state.reputation.read().unwrap();
        store.get_score(&body.peer_id)
    };

    (
        StatusCode::OK,
        Json(serde_json::json!({
            "peer_id": body.peer_id,
            "new_score": score,
            "observation_recorded": true
        })),
    ).into_response()
}

// ── Solana Stake Endpoints ───────────────────────────────────────────────────

async fn verify_stake(
    State(state): State<AppState>,
    Json(body): Json<StakeQuery>,
) -> impl IntoResponse {
    match state.solana.verify_stake(&body.wallet, body.min_stake).await {
        Ok(meets_threshold) => (
            StatusCode::OK,
            Json(StakeResponse {
                ok: true,
                balance_meets_threshold: meets_threshold,
                wallet: body.wallet,
            }),
        )
            .into_response(),
        Err(e) => (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"ok": false, "error": e})),
        )
            .into_response(),
    }
}

// ── Health ───────────────────────────────────────────────────────────────────

async fn health() -> impl IntoResponse {
    (StatusCode::OK, Json(serde_json::json!({"status": "ok", "service": "reputation_bridge"})))
}

// ── Main ─────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let solana_rpc = env::var("SOLANA_RPC_URL")
        .unwrap_or_else(|_| "https://api.mainnet-beta.solana.com".to_string());
    let listen_addr = env::var("LISTEN_ADDR")
        .unwrap_or_else(|_| "0.0.0.0:9091".to_string());

    let state = AppState {
        reputation: new_shared_store(),
        solana: Arc::new(SolanaManager::new(&solana_rpc)),
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/reputation/score", post(get_score))
        .route("/reputation/observe", post(observe_peer))
        .route("/solana/verify_stake", post(verify_stake))
        .with_state(state);

    tracing::info!("reputation_bridge listening on {listen_addr}");
    let listener = TcpListener::bind(&listen_addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
