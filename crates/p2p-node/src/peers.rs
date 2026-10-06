//! Who does the work on the network, as seen by this node: its own roles and
//! the number of connected workers.
//!
//! **Lone-worker rule.** When a single compute/verification node is on the
//! network, nobody else can check its results, so it may verify its own
//! result (if the task terms allow it). Control-plane peers (`resource`,
//! `storage`: the orchestrator) are not workers and do not count. Both sides
//! apply the rule:
//! - the worker offers to verify itself only when it sees no other worker
//!   ([`WorkerView::no_other_worker`]);
//! - the publisher accepts that offer only when the claimant is the only
//!   worker it sees, itself included ([`WorkerView::lone_worker`]).

use crate::task::PeerProfile;
use libp2p::PeerId;
use std::collections::BTreeMap;

/// Roles this node takes on (`SILICIUM_NODE_ROLES`, default `compute,verify`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct LocalRoles {
    /// Claims and computes tasks.
    pub(crate) compute: bool,
    /// Offers to verify other nodes' results.
    pub(crate) verify: bool,
}

impl LocalRoles {
    /// Roles from a comma-separated list such as `compute,verify`.
    pub(crate) fn parse(value: &str) -> Self {
        let has = |name: &str| {
            value
                .split(',')
                .any(|role| role.trim().eq_ignore_ascii_case(name))
        };
        Self {
            compute: has("compute"),
            verify: has("verify"),
        }
    }

    /// Roles of this node, read from the environment.
    pub(crate) fn from_env() -> Self {
        Self::parse(
            &std::env::var("SILICIUM_NODE_ROLES").unwrap_or_else(|_| "compute,verify".to_string()),
        )
    }

    /// True when this node computes or verifies results.
    pub(crate) fn is_worker(self) -> bool {
        self.compute || self.verify
    }
}

/// Whether a peer profile represents a node that can independently compute or
/// verify a result. Control-plane roles such as `resource` and `storage` do
/// not count for the lone-worker rule.
pub(crate) fn profile_is_worker(profile: &PeerProfile) -> bool {
    profile.roles.iter().any(|role| {
        role.trim().eq_ignore_ascii_case("compute") || role.trim().eq_ignore_ascii_case("verify")
    })
}

/// Connected peers that are workers. A peer whose heartbeat was not received
/// yet counts as a worker: in doubt, a node must not verify itself.
pub(crate) fn count_connected_workers<'a>(
    connected: impl Iterator<Item = &'a PeerId>,
    profiles: &BTreeMap<String, PeerProfile>,
) -> usize {
    connected
        .filter(|peer_id| {
            let peer_id = peer_id.to_string();
            profiles
                .values()
                .find(|profile| profile.peer_id == peer_id)
                .is_none_or(profile_is_worker)
        })
        .count()
}

/// Workers seen by this node at one instant.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct WorkerView {
    /// Connected peers that are workers (this node excluded).
    pub(crate) others: usize,
    /// Whether this node is itself a worker.
    pub(crate) local_is_worker: bool,
}

impl WorkerView {
    /// No other worker is connected: this node's own claim need not wait for
    /// others, and a lone worker may offer to verify itself.
    pub(crate) fn no_other_worker(self) -> bool {
        self.others == 0
    }

    /// At most one worker on the network, this node included: the publisher
    /// may accept a claimant's offer to verify its own result.
    pub(crate) fn lone_worker(self) -> bool {
        self.others + usize::from(self.local_is_worker) <= 1
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn profile(peer_id: &PeerId, roles: &[&str]) -> PeerProfile {
        PeerProfile {
            node_id: format!("node-{peer_id}"),
            peer_id: peer_id.to_string(),
            roles: roles.iter().map(|role| (*role).to_string()).collect(),
            app_version: "test".to_string(),
            release_channel: "dev".to_string(),
            release_build: "test".to_string(),
            capacity: json!({}),
            activity: json!({}),
            task_queue: Vec::new(),
            last_seen_unix: 0,
            last_seen_utc: String::new(),
        }
    }

    #[test]
    fn control_plane_roles_do_not_count_as_workers() {
        let peer = PeerId::random();
        assert!(!profile_is_worker(&profile(
            &peer,
            &["resource", "storage"]
        )));
        assert!(profile_is_worker(&profile(&peer, &["compute", "verify"])));
        assert!(profile_is_worker(&profile(&peer, &[" VERIFY "])));
    }

    #[test]
    fn roles_are_parsed_from_a_list() {
        assert!(LocalRoles::parse("compute, verify").is_worker());
        let orchestrator = LocalRoles::parse("resource,storage");
        assert!(!orchestrator.compute && !orchestrator.verify);
        assert!(LocalRoles::parse("Verify").verify);
    }

    #[test]
    fn unknown_peers_count_as_workers() {
        let orchestrator = PeerId::random();
        let worker = PeerId::random();
        let unknown = PeerId::random();
        let profiles = BTreeMap::from([
            ("o".to_string(), profile(&orchestrator, &["resource"])),
            ("w".to_string(), profile(&worker, &["compute"])),
        ]);
        let connected = [orchestrator, worker, unknown];
        assert_eq!(count_connected_workers(connected.iter(), &profiles), 2);
    }

    #[test]
    fn a_single_worker_behind_an_orchestrator_is_a_lone_worker() {
        // Seen by the worker: only the orchestrator is connected.
        let worker = WorkerView {
            others: 0,
            local_is_worker: true,
        };
        assert!(worker.no_other_worker() && worker.lone_worker());
        // Seen by the orchestrator (not a worker): one worker connected.
        let orchestrator = WorkerView {
            others: 1,
            local_is_worker: false,
        };
        assert!(orchestrator.lone_worker());
        assert!(!orchestrator.no_other_worker());
    }

    #[test]
    fn two_workers_must_verify_each_other() {
        let orchestrator = WorkerView {
            others: 2,
            local_is_worker: false,
        };
        assert!(!orchestrator.lone_worker());
        // A publisher that also works, with one worker connected.
        let working_publisher = WorkerView {
            others: 1,
            local_is_worker: true,
        };
        assert!(!working_publisher.lone_worker());
    }
}
