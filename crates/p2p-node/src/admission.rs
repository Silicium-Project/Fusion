//! Which tasks this node accepts, from the network and from its local API.
//!
//! - A task published on gossipsub is executed only if its (signed) source is
//!   a trusted publisher; `SILICIUM_ACCEPT_UNTRUSTED_TASKS=1` lifts that for
//!   local test networks.
//! - Every task is sanitized ([`TaskEnvelope::sanitize_remote`]): no Docker
//!   image, working directory or environment from the publisher, paths kept
//!   relative to the node's work directory, output path chosen locally.
//! - The local HTTP API needs `SILICIUM_NODE_CONTROL_TOKEN` as a bearer token
//!   when it is set, and cannot listen outside loopback without one.

use crate::task::NetworkTask;
use libp2p::PeerId;
use silicium_node_core::p2p::{RemoteTaskPolicy, TaskEnvelope};
use std::{env, net::IpAddr};

#[derive(Debug, Clone)]
pub(crate) struct SecurityConfig {
    /// Peers whose tasks are executed (`SILICIUM_TRUSTED_PUBLISHERS`, `--trusted-publisher`).
    pub(crate) trusted_publishers: Vec<PeerId>,
    /// `SILICIUM_ACCEPT_UNTRUSTED_TASKS=1`: execute tasks from any peer (test networks only).
    pub(crate) accept_untrusted_tasks: bool,
    /// `SILICIUM_ALLOW_REMOTE_WASM=1`: let tasks run a WASM module from the work directory.
    pub(crate) policy: RemoteTaskPolicy,
    /// `SILICIUM_API_BIND` (default `127.0.0.1`).
    pub(crate) api_bind: IpAddr,
    /// `SILICIUM_NODE_CONTROL_TOKEN`.
    pub(crate) control_token: Option<String>,
    /// `SILICIUM_COMPUTE_TIMEOUT_S` (default 300): bound of one compute call.
    pub(crate) compute_timeout_s: u64,
}

impl Default for SecurityConfig {
    fn default() -> Self {
        Self {
            trusted_publishers: Vec::new(),
            accept_untrusted_tasks: false,
            policy: RemoteTaskPolicy::default(),
            api_bind: IpAddr::from([127, 0, 0, 1]),
            control_token: None,
            compute_timeout_s: 300,
        }
    }
}

fn flag(key: &str) -> bool {
    env::var(key).is_ok_and(|value| matches!(value.trim(), "1" | "true" | "yes"))
}

impl SecurityConfig {
    pub(crate) fn from_env(mut trusted_publishers: Vec<PeerId>) -> Self {
        if let Ok(value) = env::var("SILICIUM_TRUSTED_PUBLISHERS") {
            trusted_publishers.extend(crate::config::parse_peer_ids(&value));
        }
        let defaults = Self::default();
        Self {
            trusted_publishers,
            accept_untrusted_tasks: flag("SILICIUM_ACCEPT_UNTRUSTED_TASKS"),
            policy: RemoteTaskPolicy {
                allow_wasm: flag("SILICIUM_ALLOW_REMOTE_WASM"),
            },
            api_bind: env::var("SILICIUM_API_BIND")
                .ok()
                .and_then(|value| value.trim().parse().ok())
                .unwrap_or(defaults.api_bind),
            control_token: env::var("SILICIUM_NODE_CONTROL_TOKEN")
                .ok()
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty()),
            compute_timeout_s: env::var("SILICIUM_COMPUTE_TIMEOUT_S")
                .ok()
                .and_then(|value| value.trim().parse().ok())
                .unwrap_or(defaults.compute_timeout_s),
        }
    }

    /// The API must not be reachable from other machines without a token.
    pub(crate) fn check_api_exposure(&self) -> Result<(), String> {
        if !self.api_bind.is_loopback() && self.control_token.is_none() {
            return Err(format!(
                "SILICIUM_NODE_CONTROL_TOKEN is required to bind the API on {}",
                self.api_bind
            ));
        }
        Ok(())
    }

    /// Accepts or refuses a task received from gossipsub.
    pub(crate) fn admit_remote(
        &self,
        source: Option<PeerId>,
        local_peer_id: PeerId,
        envelope: TaskEnvelope,
    ) -> Result<NetworkTask, String> {
        let trusted = match source {
            Some(peer) => peer == local_peer_id || self.trusted_publishers.contains(&peer),
            None => false,
        };
        if !trusted && !self.accept_untrusted_tasks {
            return Err(format!(
                "untrusted_task_publisher:{}",
                source
                    .map(|peer| peer.to_string())
                    .unwrap_or_else(|| "anonymous".to_string())
            ));
        }
        self.admit_local(envelope)
    }

    /// Sanitizes a task (local API or admitted remote task).
    pub(crate) fn admit_local(&self, envelope: TaskEnvelope) -> Result<NetworkTask, String> {
        envelope
            .sanitize_remote(&self.policy)
            .map(NetworkTask::from)
            .map_err(|error| error.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn envelope() -> TaskEnvelope {
        TaskEnvelope {
            task_id: "job-1".to_string(),
            scene_path: "scenes/demo.cfg".to_string(),
            output_path: "/tmp/anything.ppm".to_string(),
            seed: "1".to_string(),
            hardware_hint: None,
            runtime_hint: None,
            runtime_args: Vec::new(),
            runtime_env: BTreeMap::new(),
            runtime_workdir: None,
            runtime_module_path: None,
            runtime_image: None,
            scene_sha256: None,
        }
    }

    #[test]
    fn only_trusted_publishers_are_executed_by_default() {
        let local = PeerId::random();
        let trusted = PeerId::random();
        let stranger = PeerId::random();
        let config = SecurityConfig {
            trusted_publishers: vec![trusted],
            ..SecurityConfig::default()
        };
        assert!(
            config
                .admit_remote(Some(trusted), local, envelope())
                .is_ok()
        );
        assert!(config.admit_remote(Some(local), local, envelope()).is_ok());
        assert!(
            config
                .admit_remote(Some(stranger), local, envelope())
                .is_err()
        );
        assert!(config.admit_remote(None, local, envelope()).is_err());

        let open = SecurityConfig {
            accept_untrusted_tasks: true,
            ..SecurityConfig::default()
        };
        assert!(open.admit_remote(Some(stranger), local, envelope()).is_ok());
    }

    #[test]
    fn admitted_tasks_are_sanitized() {
        let config = SecurityConfig {
            accept_untrusted_tasks: true,
            ..SecurityConfig::default()
        };
        let task = config
            .admit_remote(None, PeerId::random(), envelope())
            .unwrap();
        assert_eq!(task.output_path, "job-1/output.ppm");
        let docker = TaskEnvelope {
            runtime_image: Some("evil".to_string()),
            ..envelope()
        };
        assert!(config.admit_local(docker).is_err());
    }

    #[test]
    fn api_outside_loopback_needs_a_token() {
        let exposed = SecurityConfig {
            api_bind: IpAddr::from([0, 0, 0, 0]),
            ..SecurityConfig::default()
        };
        assert!(exposed.check_api_exposure().is_err());
        let protected = SecurityConfig {
            control_token: Some("t".to_string()),
            ..exposed
        };
        assert!(protected.check_api_exposure().is_ok());
        assert!(SecurityConfig::default().check_api_exposure().is_ok());
    }
}
