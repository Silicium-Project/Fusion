//! Configuration from the environment.

use std::{env, net::SocketAddr, path::PathBuf, time::Duration};

#[derive(Debug, Clone)]
pub struct Config {
    /// `SILICIUM_COMPUTE_BIND` (default `127.0.0.1:9090`).
    pub bind: String,
    /// `SILICIUM_RAYTRACER_BIN`: native renderer; required by `/compute`.
    pub raytracer_bin: Option<PathBuf>,
    /// `SILICIUM_COMPUTE_ROOT`: every request path is resolved inside it
    /// (default `$SILICIUM_DATA_DIR/work`, else `./work`).
    pub root: PathBuf,
    /// `SILICIUM_COMPUTE_TIMEOUT_S`: renderer timeout (default 300 s).
    pub timeout: Duration,
    /// `SILICIUM_COMPUTE_TOKEN`: when set, requests need `Authorization: Bearer <token>`.
    pub token: Option<String>,
}

impl Config {
    pub fn from_env() -> Result<Self, String> {
        let get = |key: &str| {
            env::var(key)
                .ok()
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty())
        };
        let bind = get("SILICIUM_COMPUTE_BIND").unwrap_or_else(|| "127.0.0.1:9090".to_string());
        let address: SocketAddr = bind
            .parse()
            .map_err(|_| format!("invalid SILICIUM_COMPUTE_BIND: {bind}"))?;
        let token = get("SILICIUM_COMPUTE_TOKEN");
        if !address.ip().is_loopback() && token.is_none() {
            return Err(
                "SILICIUM_COMPUTE_TOKEN is required when binding outside loopback".to_string(),
            );
        }
        let root = get("SILICIUM_COMPUTE_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                get("SILICIUM_DATA_DIR")
                    .map(|dir| PathBuf::from(dir).join("work"))
                    .unwrap_or_else(|| PathBuf::from("work"))
            });
        std::fs::create_dir_all(&root)
            .map_err(|error| format!("cannot create {}: {error}", root.display()))?;
        let timeout_s = match get("SILICIUM_COMPUTE_TIMEOUT_S") {
            Some(value) => value
                .parse::<u64>()
                .map_err(|_| format!("invalid SILICIUM_COMPUTE_TIMEOUT_S: {value}"))?,
            None => 300,
        };
        Ok(Self {
            bind,
            raytracer_bin: get("SILICIUM_RAYTRACER_BIN").map(PathBuf::from),
            root,
            timeout: Duration::from_secs(timeout_s.max(1)),
            token,
        })
    }
}
