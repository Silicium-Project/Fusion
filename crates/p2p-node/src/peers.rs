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
use std::{
    collections::{BTreeMap, BTreeSet},
    time::{SystemTime, UNIX_EPOCH},
};

/// Heartbeats are sent every five seconds; older profiles are treated as offline.
pub(crate) const PROFILE_STALE_AFTER_SECONDS: i64 = 15;

pub(crate) fn current_unix_seconds() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or_default()
}

pub(crate) fn profile_is_fresh(profile: &PeerProfile, now_unix: i64) -> bool {
    profile.last_seen_unix > 0
        && now_unix.saturating_sub(profile.last_seen_unix) <= PROFILE_STALE_AFTER_SECONDS
}

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

/// Whether a peer can accept compute tasks. A verifier-only node must not
/// increase the estimated value of delegation.
fn profile_can_compute(profile: &PeerProfile) -> bool {
    profile
        .roles
        .iter()
        .any(|role| role.trim().eq_ignore_ascii_case("compute"))
}

/// Workers visible through live signed gossip or a direct connection. Unknown
/// direct peers count as workers so missing profiles cannot enable self-checks.
pub(crate) fn count_online_workers<'a>(
    local_peer_id: &str,
    connected: impl Iterator<Item = &'a PeerId>,
    profiles: &BTreeMap<String, PeerProfile>,
    now_unix: i64,
) -> usize {
    let mut workers = BTreeSet::new();
    for profile in profiles.values() {
        if profile.peer_id != local_peer_id
            && profile_is_worker(profile)
            && profile_is_fresh(profile, now_unix)
        {
            workers.insert(profile.peer_id.clone());
        }
    }
    for peer_id in connected {
        let peer_id = peer_id.to_string();
        if peer_id == local_peer_id {
            continue;
        }
        let profile = profiles.values().find(|profile| profile.peer_id == peer_id);
        if profile.is_none_or(profile_is_worker) {
            workers.insert(peer_id);
        }
    }
    workers.len()
}

/// Task-book authors for compute peers whose signed heartbeats recently
/// crossed the gossip mesh. Direct connectivity is not required: task and
/// TaskBook messages also cross that mesh through relays.
pub(crate) fn online_compute_authors(
    local_peer_id: &str,
    profiles: &BTreeMap<String, PeerProfile>,
    now_unix: i64,
) -> Vec<Option<String>> {
    let mut seen_peers = BTreeSet::new();
    let mut seen_authors = BTreeSet::new();
    profiles
        .values()
        .filter(|profile| {
            profile.peer_id != local_peer_id
                && profile_is_fresh(profile, now_unix)
                && profile_can_compute(profile)
                && !profile.task_author.trim().is_empty()
                && seen_peers.insert(profile.peer_id.clone())
                && seen_authors.insert(profile.task_author.clone())
        })
        .map(|profile| Some(profile.task_author.clone()))
        .collect()
}

/// Workers seen by this node at one instant.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct WorkerView {
    /// Other live workers visible through direct connection or signed gossip.
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
            task_author: String::new(),
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
    fn live_gossiped_workers_and_unknown_direct_peers_are_counted_once() {
        let orchestrator = PeerId::random();
        let worker = PeerId::random();
        let relayed_worker = PeerId::random();
        let stale_worker = PeerId::random();
        let local = PeerId::random();
        let unknown = PeerId::random();
        let mut live_worker = profile(&worker, &["compute"]);
        live_worker.last_seen_unix = 990;
        let mut relayed = profile(&relayed_worker, &["verify"]);
        relayed.last_seen_unix = 995;
        let mut stale = profile(&stale_worker, &["compute"]);
        stale.last_seen_unix = 970;
        let mut service = profile(&orchestrator, &["resource", "storage"]);
        service.last_seen_unix = 999;
        let profiles = BTreeMap::from([
            ("o".to_string(), service),
            ("w".to_string(), live_worker),
            ("relay".to_string(), relayed),
            ("stale".to_string(), stale),
            ("self".to_string(), profile(&local, &["compute"])),
        ]);
        let connected = [orchestrator, worker, unknown];
        assert_eq!(
            count_online_workers(&local.to_string(), connected.iter(), &profiles, 1_000),
            3
        );
    }

    #[test]
    fn only_fresh_mesh_compute_peers_are_delegation_candidates() {
        let compute = PeerId::random();
        let verifier = PeerId::random();
        let orchestrator = PeerId::random();
        let local = PeerId::random();
        let mut compute_profile = profile(&compute, &["compute", "verify"]);
        compute_profile.task_author = "compute-author".to_string();
        compute_profile.last_seen_unix = 999;
        let mut verifier_profile = profile(&verifier, &["verify"]);
        verifier_profile.task_author = "verify-author".to_string();
        verifier_profile.last_seen_unix = 999;
        let mut service_profile = profile(&orchestrator, &["resource", "storage"]);
        service_profile.task_author = "service-author".to_string();
        service_profile.last_seen_unix = 999;
        let profiles = BTreeMap::from([
            ("compute".to_string(), compute_profile),
            ("verifier".to_string(), verifier_profile),
            ("orchestrator".to_string(), service_profile),
        ]);
        assert_eq!(
            online_compute_authors(&local.to_string(), &profiles, 1_000),
            vec![Some("compute-author".to_string())]
        );

        let stale = PeerId::random();
        let mut stale_profile = profile(&stale, &["compute"]);
        stale_profile.task_author = "stale-author".to_string();
        stale_profile.last_seen_unix = 970;
        let mut profiles = profiles;
        profiles.insert("stale".to_string(), stale_profile);
        assert_eq!(
            online_compute_authors(&local.to_string(), &profiles, 1_000),
            vec![Some("compute-author".to_string())]
        );
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
