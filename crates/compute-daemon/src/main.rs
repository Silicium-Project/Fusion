//! `compute_daemon`: local HTTP service that renders and verifies raytracer
//! tiles for the node.
//!
//! - `POST /compute` runs `SILICIUM_RAYTRACER_BIN` on a tile (with a timeout),
//!   checks the PPM and returns its pixel hash and row-milestone commitment.
//! - `POST /verify` re-checks a sample of those milestones; the sample shrinks
//!   as the worker's reputation grows.
//! - `GET /health`.
//!
//! File paths in requests are relative to `SILICIUM_COMPUTE_ROOT`: a caller can
//! never make the daemon read or write elsewhere. The tile logic itself lives
//! in the `silicium_raytracer::pipeline` library.

mod api;
mod config;

use config::Config;
use tokio::net::TcpListener;

#[tokio::main]
async fn main() {
    let config = match Config::from_env() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("compute_daemon_config_error:{error}"); // i18n:ignore -- operator log
            std::process::exit(2);
        }
    };
    let bind = config.bind.clone();
    let listener = match TcpListener::bind(&bind).await {
        Ok(listener) => listener,
        Err(error) => {
            eprintln!("compute_daemon_bind_error:{bind}:{error}"); // i18n:ignore -- operator log
            std::process::exit(2);
        }
    };
    println!(
        "compute_daemon listening on {bind}, root {}",
        config.root.display()
    ); // i18n:ignore -- operator log
    if let Err(error) = axum::serve(listener, api::router(config)).await {
        eprintln!("compute_daemon_stopped:{error}"); // i18n:ignore -- operator log
    }
}
