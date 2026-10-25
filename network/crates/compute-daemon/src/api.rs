//! HTTP routes.

use crate::config::Config;
use axum::{
    Json, Router,
    extract::{Request, State},
    http::{StatusCode, header},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use serde::Deserialize;
use serde_json::{Value, json};
use silicium_node_core::sandbox;
use silicium_raytracer::pipeline::{milestones, ppm, sampling};
use std::{path::PathBuf, sync::Arc};
use tokio::process::Command;

#[derive(Deserialize)]
pub struct ComputeRequest {
    scene_path: String,
    output_path: String,
    y_start: Option<u32>,
    y_end: Option<u32>,
    x_start: Option<u32>,
    x_end: Option<u32>,
    /// Rows per milestone (default 20).
    batch_rows: Option<usize>,
}

#[derive(Deserialize)]
pub struct VerifyRequest {
    ppm_path: String,
    manifest: sampling::SampledManifest,
    seed: String,
    reputation: Option<f64>,
}

pub fn router(config: Config) -> Router {
    let state = Arc::new(config);
    Router::new()
        .route("/compute", post(compute))
        .route("/verify", post(verify))
        .route_layer(middleware::from_fn_with_state(state.clone(), require_token))
        .route("/health", get(health))
        .with_state(state)
}

async fn health() -> Json<Value> {
    Json(json!({"status": "ok", "service": "compute_daemon"}))
}

async fn require_token(
    State(config): State<Arc<Config>>,
    request: Request,
    next: Next,
) -> Response {
    if let Some(token) = &config.token {
        let expected = format!("Bearer {token}");
        let given = request
            .headers()
            .get(header::AUTHORIZATION)
            .and_then(|value| value.to_str().ok());
        if given != Some(expected.as_str()) {
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({"error": "unauthorized"})),
            )
                .into_response();
        }
    }
    next.run(request).await
}

fn compute_error(message: impl Into<String>) -> Json<Value> {
    Json(json!({"status": "error", "hash": null, "error": message.into()}))
}

fn inside(config: &Config, relative: &str) -> Result<PathBuf, String> {
    sandbox::resolve(&config.root, relative).map_err(|error| error.to_string())
}

async fn compute(
    State(config): State<Arc<Config>>,
    Json(request): Json<ComputeRequest>,
) -> Json<Value> {
    let Some(binary) = config.raytracer_bin.clone() else {
        return compute_error("SILICIUM_RAYTRACER_BIN not set");
    };
    let (scene, output) = match (
        inside(&config, &request.scene_path),
        inside(&config, &request.output_path),
    ) {
        (Ok(scene), Ok(output)) => (scene, output),
        (Err(error), _) | (_, Err(error)) => return compute_error(error),
    };
    if let Some(parent) = output.parent()
        && let Err(error) = tokio::fs::create_dir_all(parent).await
    {
        return compute_error(error.to_string());
    }
    let mut command = Command::new(&binary);
    command
        .arg(&scene)
        .arg("--output")
        .arg(&output)
        .kill_on_drop(true);
    for (flag, value) in [
        ("--y-start", request.y_start),
        ("--y-end", request.y_end),
        ("--x-start", request.x_start),
        ("--x-end", request.x_end),
    ] {
        if let Some(value) = value {
            command.arg(flag).arg(value.to_string());
        }
    }
    match tokio::time::timeout(config.timeout, command.output()).await {
        Err(_) => return compute_error(format!("raytracer_timeout:{}s", config.timeout.as_secs())),
        Ok(Err(error)) => return compute_error(error.to_string()),
        Ok(Ok(result)) if !result.status.success() => {
            return compute_error(String::from_utf8_lossy(&result.stderr).to_string());
        }
        Ok(Ok(_)) => {}
    }
    let bytes = match tokio::fs::read(&output).await {
        Ok(bytes) => bytes,
        Err(error) => return compute_error(error.to_string()),
    };
    let image = match ppm::parse(&bytes, &request.output_path) {
        Ok(image) => image,
        Err(error) => return compute_error(format!("raytracer_compute_invalid_output:{error}")),
    };
    let manifest = milestones::build(
        &bytes,
        request.y_start.unwrap_or(0) as usize,
        request
            .batch_rows
            .unwrap_or(milestones::DEFAULT_VERIFICATION_BATCH_ROWS),
        request.x_start.unwrap_or(0) as usize,
    );
    match manifest {
        Ok(manifest) => Json(json!({
            "status": "success",
            "hash": silicium_raytracer::pipeline::sha256_hex(&image.pixels),
            "width": image.width,
            "height": image.height,
            "milestones": manifest,
            "error": null,
        })),
        Err(error) => compute_error(error),
    }
}

async fn verify(
    State(config): State<Arc<Config>>,
    Json(request): Json<VerifyRequest>,
) -> Json<Value> {
    let failure = |reason: String| {
        Json(json!({
            "verified": false,
            "escalated_to_full": true,
            "sample_rate": 0.0,
            "sampled_count": 0,
            "total_milestones": 0,
            "failed_milestones": [],
            "reason": reason,
        }))
    };
    let path = match inside(&config, &request.ppm_path) {
        Ok(path) => path,
        Err(error) => return failure(error),
    };
    let bytes = match tokio::fs::read(&path).await {
        Ok(bytes) => bytes,
        Err(error) => return failure(format!("Failed to read ppm: {error}")),
    };
    match sampling::verify(
        &bytes,
        &request.manifest,
        &request.seed,
        request.reputation.unwrap_or(50.0),
    ) {
        Ok(result) => Json(serde_json::to_value(result).unwrap_or_default()),
        Err(error) => failure(format!("Invalid ppm: {error}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use std::time::Duration;
    use tower::ServiceExt;

    fn config(root: PathBuf, token: Option<&str>) -> Config {
        std::fs::create_dir_all(&root).unwrap();
        Config {
            bind: "127.0.0.1:0".to_string(),
            raytracer_bin: None,
            root,
            timeout: Duration::from_secs(5),
            token: token.map(str::to_string),
        }
    }

    fn temp_root(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!("compute-daemon-{name}-{}", std::process::id()))
    }

    async fn call(app: Router, uri: &str, body: Value, token: Option<&str>) -> (StatusCode, Value) {
        let mut builder =
            axum::http::Request::post(uri).header(header::CONTENT_TYPE, "application/json");
        if let Some(token) = token {
            builder = builder.header(header::AUTHORIZATION, format!("Bearer {token}"));
        }
        let response = app
            .oneshot(builder.body(Body::from(body.to_string())).unwrap())
            .await
            .unwrap();
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        (
            status,
            serde_json::from_slice(&bytes).unwrap_or(Value::Null),
        )
    }

    #[tokio::test]
    async fn verify_checks_milestones_inside_the_root_only() {
        let root = temp_root("verify");
        let pixels: Vec<u8> = (0..4 * 6 * 3).map(|index| index as u8).collect();
        let tile = ppm::encode(4, 6, &pixels);
        std::fs::write(root.join("tile.ppm"), &tile).ok();
        let app = router(config(root.clone(), None));
        std::fs::write(root.join("tile.ppm"), &tile).unwrap();
        let manifest = milestones::build(&tile, 10, 2, 0).unwrap();
        let body =
            json!({"ppm_path": "tile.ppm", "manifest": manifest, "seed": "s", "reputation": 0.0});
        let (status, result) = call(app.clone(), "/verify", body, None).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(result["verified"], true);
        assert_eq!(result["sampled_count"], 3);

        let escape = json!({"ppm_path": "../outside.ppm", "manifest": manifest, "seed": "s"});
        let (_, result) = call(app, "/verify", escape, None).await;
        assert_eq!(result["verified"], false);
        assert!(
            result["reason"]
                .as_str()
                .unwrap()
                .starts_with("sandbox_path_escapes_root")
        );
        std::fs::remove_dir_all(root).ok();
    }

    #[tokio::test]
    async fn compute_refuses_absolute_paths_and_missing_binary() {
        let root = temp_root("compute");
        let app = router(config(root.clone(), None));
        let body = json!({"scene_path": "/etc/passwd", "output_path": "out.ppm"});
        let (_, result) = call(app, "/compute", body, None).await;
        assert_eq!(result["status"], "error");
        std::fs::remove_dir_all(root).ok();
    }

    #[tokio::test]
    async fn token_is_required_when_configured_but_not_for_health() {
        let root = temp_root("token");
        let app = router(config(root.clone(), Some("secret")));
        let body = json!({"ppm_path": "x.ppm", "manifest": {}, "seed": "s"});
        let (status, _) = call(app.clone(), "/verify", body.clone(), None).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        let (status, _) = call(app.clone(), "/verify", body, Some("secret")).await;
        assert_eq!(status, StatusCode::OK);
        let response = app
            .oneshot(
                axum::http::Request::get("/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        std::fs::remove_dir_all(root).ok();
    }
}
