//! Which tasks this node accepts, from the network and from its local API.
//!
//! - A root task published on gossipsub is executed only if its source is a
//!   trusted publisher: `SILICIUM_TRUSTED_PUBLISHERS`, `--trusted-publisher`,
//!   or a peer id pinned in a bootstrap address (`.../p2p/<peer id>`). A child
//!   task can also be admitted when its exact envelope is committed by a
//!   TaskBook proposal signed by a worker accepted on the known parent task.
//!   `SILICIUM_ACCEPT_UNTRUSTED_TASKS=1` remains for local test networks only;
//!   the node refuses to start with it on the `dev` and `prod` channels.
//! - Every task is sanitized ([`TaskEnvelope::sanitize_remote`]): no Docker
//!   image, working directory or environment from the publisher, paths kept
//!   relative to the node's work directory, output path chosen locally; its
//!   workload must be one this node knows ([`crate::workload`]).
//! - The local HTTP API needs `SILICIUM_NODE_CONTROL_TOKEN` as a bearer token
//!   when it is set, and cannot listen outside loopback without one.

use crate::{processing::NodeContext, task::NetworkTask};
use libp2p::PeerId;
use silicium_node_core::{
    p2p::{DhtRecordEnvelope, RemoteTaskPolicy, TaskEnvelope},
    taskbook::{TaskEvent, TaskEventBody},
};
use std::{env, net::IpAddr};

const MAX_DELEGATION_DEPTH: u8 = 4;

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

    /// Accepting tasks from any peer is for local test networks only: it is
    /// refused on the released channels (`SILICIUM_RELEASE_CHANNEL` `dev` or
    /// `prod`).
    pub(crate) fn check_untrusted_tasks(&self, release_channel: &str) -> Result<(), String> {
        let released = matches!(release_channel.trim(), "dev" | "prod");
        if self.accept_untrusted_tasks && released {
            return Err(format!(
                "SILICIUM_ACCEPT_UNTRUSTED_TASKS is refused on the {} channel: pin the \
                 orchestrator in the bootstrap address (/p2p/<peer id>) or set \
                 SILICIUM_TRUSTED_PUBLISHERS",
                release_channel.trim()
            ));
        }
        Ok(())
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

    /// Accepts a task from an approved publisher, or a recursively delegated
    /// child whose proposal is signed by the accepted claimant of its parent.
    pub(crate) fn admit_received(
        &self,
        context: &NodeContext,
        source: Option<PeerId>,
        local_peer_id: PeerId,
        envelope: TaskEnvelope,
    ) -> Result<NetworkTask, String> {
        let trusted = source
            .is_some_and(|peer| peer == local_peer_id || self.trusted_publishers.contains(&peer));
        if trusted || self.accept_untrusted_tasks {
            let mut task = self.admit_remote(source, local_peer_id, envelope)?;
            if task.parent_task_id.is_none() && task.delegation_depth == 0 {
                task.root_job_id.get_or_insert_with(|| task.task_id.clone());
            }
            return Ok(task);
        }
        admit_delegated(context, envelope, &self.policy)
    }

    /// Sanitizes a task (local API or admitted remote task) and refuses a
    /// workload this node does not know.
    pub(crate) fn admit_local(&self, envelope: TaskEnvelope) -> Result<NetworkTask, String> {
        let task = envelope
            .sanitize_remote(&self.policy)
            .map(NetworkTask::from)
            .map_err(|error| error.to_string())?;
        if crate::workload::of(&task).is_none() {
            return Err(format!(
                "unknown_workload:{}",
                task.workload.as_deref().unwrap_or_default()
            ));
        }
        Ok(task)
    }
}

/// A worker may publish child tasks only after it has an accepted claim on the
/// parent. The replicated TaskBook proposal binds the exact envelope bytes;
/// recomputing the workload split prevents a claimant from turning that
/// authorization into arbitrary remote work.
fn admit_delegated(
    context: &NodeContext,
    envelope: TaskEnvelope,
    policy: &RemoteTaskPolicy,
) -> Result<NetworkTask, String> {
    let task = envelope
        .sanitize_remote(policy)
        .map(NetworkTask::from)
        .map_err(|error| error.to_string())?;
    let parent_id = task
        .parent_task_id
        .as_deref()
        .ok_or_else(|| "delegation_parent_missing".to_string())?;
    let parent = context
        .known_tasks
        .lock()
        .map_err(|_| "delegation_parent_state_unavailable".to_string())?
        .get(parent_id)
        .cloned()
        .ok_or_else(|| "delegation_parent_pending".to_string())?;
    let expected_depth = parent.delegation_depth.saturating_add(1);
    if expected_depth > MAX_DELEGATION_DEPTH || task.delegation_depth != expected_depth {
        return Err("delegation_depth_invalid".to_string());
    }
    let root_job_id = parent
        .root_job_id
        .clone()
        .unwrap_or_else(|| parent.task_id.clone());
    if task.root_job_id.as_deref() != Some(root_job_id.as_str()) {
        return Err("delegation_root_mismatch".to_string());
    }

    let proposal_bytes = serde_json::to_vec(&envelope)
        .map_err(|error| format!("delegation_envelope_invalid:{error}"))?;
    let proposal_hash = TaskEvent::payload_hash(&proposal_bytes);
    let proposals = context
        .taskbook
        .with_book(|book| {
            book.events()
                .filter(|event| {
                    event.task_id == task.task_id
                        && matches!(event.body, TaskEventBody::TaskProposed { .. })
                })
                .cloned()
                .collect::<Vec<_>>()
        })
        .map_err(|error| error.to_string())?;
    if proposals.is_empty() {
        return Err("delegation_proposal_pending".to_string());
    }
    let proposal_author = proposals
        .iter()
        .find_map(|event| {
            if !TaskEvent::owns_task(&event.author, &task.task_id) {
                return None;
            }
            match &event.body {
                TaskEventBody::TaskProposed { spec, .. }
                    if spec.sha256 == proposal_hash
                        && spec.uri == DhtRecordEnvelope::task_record_key(&task.task_id) =>
                {
                    Some(event.author.clone())
                }
                _ => None,
            }
        })
        .ok_or_else(|| "delegation_proposal_mismatch".to_string())?;
    let parent_state = context
        .taskbook
        .state(parent_id)
        .map_err(|error| error.to_string())?
        .ok_or_else(|| "delegation_parent_proposal_pending".to_string())?;
    if !parent_state
        .attempts
        .iter()
        .any(|attempt| attempt.claimant == proposal_author)
    {
        return Err("delegation_author_not_accepted_parent_claimant".to_string());
    }

    let scene_hash = parent
        .scene_sha256
        .as_deref()
        .ok_or_else(|| "delegation_parent_input_unhashed".to_string())?;
    if !context.content.has(scene_hash) {
        return Err("delegation_parent_input_not_available".to_string());
    }
    let workload = crate::workload::of(&parent)
        .ok_or_else(|| "delegation_parent_workload_unknown".to_string())?;
    let input = context.content.absolute(&parent.scene_path);
    let (_, children) = workload
        .split_subtask(&parent, &input, &context.job_settings)
        .ok_or_else(|| "delegation_parent_cannot_split".to_string())?;
    if children.len() != 2 {
        return Err("delegation_split_not_binary".to_string());
    }
    let payment_indexes = match parent.solana_payment.as_ref() {
        Some(payment) => {
            let index = payment
                .fragment_index
                .ok_or_else(|| "delegation_payment_parent_index_missing".to_string())?;
            Some(
                crate::worker::child_fragment_indexes(payment.expected_fragments, index)
                    .ok_or_else(|| "delegation_payment_capacity_exceeded".to_string())?,
            )
        }
        None => None,
    };
    for (index, mut expected) in children.into_iter().enumerate() {
        expected.parent_task_id = Some(parent.task_id.clone());
        expected.root_job_id = Some(root_job_id.clone());
        expected.delegation_depth = expected_depth;
        if let (Some(payment), Some(indexes)) = (parent.solana_payment.as_ref(), payment_indexes) {
            let mut child_payment = payment.clone();
            child_payment.fragment_index = Some(indexes[index]);
            expected.solana_payment = Some(child_payment);
        }
        if same_delegated_payload(&expected, &task) {
            return Ok(task);
        }
    }
    Err("delegation_child_does_not_match_parent_split".to_string())
}

fn same_delegated_payload(expected: &NetworkTask, actual: &NetworkTask) -> bool {
    expected.root_job_id == actual.root_job_id
        && expected.parent_task_id == actual.parent_task_id
        && expected.delegation_depth == actual.delegation_depth
        && expected.scene_path == actual.scene_path
        && expected.seed == actual.seed
        && expected.hardware_hint == actual.hardware_hint
        && expected.runtime_hint == actual.runtime_hint
        && expected.runtime_args == actual.runtime_args
        && expected.runtime_env == actual.runtime_env
        && expected.runtime_workdir == actual.runtime_workdir
        && expected.runtime_module_path == actual.runtime_module_path
        && expected.runtime_image == actual.runtime_image
        && expected.scene_sha256 == actual.scene_sha256
        && expected.region == actual.region
        && expected.workload == actual.workload
        && expected.solana_payment == actual.solana_payment
        && expected.byte_range == actual.byte_range
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn envelope() -> TaskEnvelope {
        TaskEnvelope {
            task_id: "job-1".to_string(),
            root_job_id: None,
            parent_task_id: None,
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
            region: None,
            workload: None,
            solana_payment: None,
            byte_range: None,
            delegation_depth: 0,
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
    fn untrusted_tasks_are_refused_on_released_channels() {
        let open = SecurityConfig {
            accept_untrusted_tasks: true,
            ..SecurityConfig::default()
        };
        assert!(open.check_untrusted_tasks("dev").is_err());
        assert!(open.check_untrusted_tasks("prod").is_err());
        assert!(open.check_untrusted_tasks("local").is_ok());
        assert!(open.check_untrusted_tasks("").is_ok());
        assert!(
            SecurityConfig::default()
                .check_untrusted_tasks("prod")
                .is_ok()
        );
    }

    #[test]
    fn unknown_workloads_are_refused() {
        let config = SecurityConfig {
            accept_untrusted_tasks: true,
            ..SecurityConfig::default()
        };
        let sha = TaskEnvelope {
            workload: Some("calcul/integrity/sha256".to_string()),
            ..envelope()
        };
        let task = config.admit_local(sha).unwrap();
        assert_eq!(task.output_path, "job-1/output.bin");
        let unknown = TaskEnvelope {
            workload: Some("calcul/unknown".to_string()),
            ..envelope()
        };
        assert_eq!(
            config.admit_local(unknown).unwrap_err(),
            "unknown_workload:calcul/unknown"
        );
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
