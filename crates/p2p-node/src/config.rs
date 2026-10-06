//! Node configuration: command-line flags, environment variables and the
//! local hardware bucket. CLI flags win over environment variables.

use crate::admission::SecurityConfig;
use libp2p::{Multiaddr, PeerId};
use silicium_node_core::hardware::{
    GpuAcceleration, HardwareBucket, HardwareProfile, OperatingSystem, SimdWidth, VramClass,
};
use std::{env, path::PathBuf};

#[derive(Debug, Clone)]
pub(crate) struct NodeConfig {
    pub(crate) bootstrap_peers: Vec<Multiaddr>,
    pub(crate) data_dir: PathBuf,
    pub(crate) api_port: u16,
    pub(crate) p2p_bind: std::net::IpAddr,
    pub(crate) p2p_port: u16,
    pub(crate) enable_quic_listener: bool,
    pub(crate) dispatcher_seed: u64,
    pub(crate) security: SecurityConfig,
}

#[derive(Debug, Default)]
pub(crate) struct NodeCliOverrides {
    pub(crate) bootstrap_peers: Vec<Multiaddr>,
    pub(crate) data_dir: Option<PathBuf>,
    pub(crate) api_port: Option<u16>,
    pub(crate) p2p_bind: Option<std::net::IpAddr>,
    pub(crate) p2p_port: Option<u16>,
    pub(crate) enable_quic_listener: Option<bool>,
    pub(crate) dispatcher_seed: Option<u64>,
    pub(crate) trusted_publishers: Vec<PeerId>,
}

/// Comma-separated peer ids; invalid entries are reported and skipped.
pub(crate) fn parse_peer_ids(value: &str) -> Vec<PeerId> {
    value
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .filter_map(|item| match item.parse::<PeerId>() {
            Ok(peer) => Some(peer),
            Err(_) => {
                eprintln!(" Ignoring invalid trusted publisher peer id: {item}"); // i18n:ignore -- operator log
                None
            }
        })
        .collect()
}

/// Peer ids pinned in bootstrap addresses (`.../p2p/<peer id>`). The node
/// already trusts its bootstrap peer as its entry point, and the Noise
/// handshake proves that identity, so the orchestrator named this way is a
/// trusted publisher without a separate `SILICIUM_TRUSTED_PUBLISHERS`.
pub(crate) fn bootstrap_peer_ids(addresses: &[Multiaddr]) -> Vec<PeerId> {
    addresses
        .iter()
        .filter_map(|address| {
            address.iter().find_map(|protocol| match protocol {
                libp2p::multiaddr::Protocol::P2p(peer_id) => Some(peer_id),
                _ => None,
            })
        })
        .collect()
}

pub(crate) fn parse_bootstrap_peer(value: &str) -> Vec<Multiaddr> {
    value
        .split(',')
        .filter_map(|item| item.trim().parse::<Multiaddr>().ok())
        .collect()
}

pub(crate) fn parse_node_cli_args<I>(args: I) -> NodeCliOverrides
where
    I: IntoIterator<Item = String>,
{
    let mut overrides = NodeCliOverrides::default();
    let mut args = args.into_iter().peekable();

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--bootstrap-peer" => {
                if let Some(value) = args.next() {
                    overrides
                        .bootstrap_peers
                        .extend(parse_bootstrap_peer(&value));
                }
            }
            "--bootstrap-peers" => {
                if let Some(value) = args.next() {
                    overrides
                        .bootstrap_peers
                        .extend(parse_bootstrap_peer(&value));
                }
            }
            "--trusted-publisher" | "--trusted-publishers" => {
                if let Some(value) = args.next() {
                    overrides.trusted_publishers.extend(parse_peer_ids(&value));
                }
            }
            _ if arg.starts_with("--trusted-publisher=")
                || arg.starts_with("--trusted-publishers=") =>
            {
                if let Some((_, value)) = arg.split_once('=') {
                    overrides.trusted_publishers.extend(parse_peer_ids(value));
                }
            }
            "--api-port" => {
                if let Some(value) = args.next() {
                    overrides.api_port = value.parse::<u16>().ok();
                }
            }
            "--p2p-bind" => {
                if let Some(value) = args.next() {
                    overrides.p2p_bind = value.parse().ok();
                }
            }
            "--p2p-port" => {
                if let Some(value) = args.next() {
                    overrides.p2p_port = value.parse::<u16>().ok();
                }
            }
            "--data-dir" => {
                if let Some(value) = args.next() {
                    overrides.data_dir = Some(PathBuf::from(value));
                }
            }
            "--dispatcher-seed" => {
                if let Some(value) = args.next() {
                    overrides.dispatcher_seed = value.parse::<u64>().ok();
                }
            }
            "--disable-quic" => {
                overrides.enable_quic_listener = Some(false);
            }
            "--enable-quic" => {
                overrides.enable_quic_listener = Some(true);
            }
            "--help" | "-h" => {
                println!(
                    "Usage: p2p_node [--bootstrap-peer <multiaddr>] [--api-port <port>] [--p2p-bind <ip>] [--p2p-port <port>] [--data-dir <path>] [--dispatcher-seed <seed>] [--enable-quic|--disable-quic] [--trusted-publisher <peer-id>]"
                );
                std::process::exit(0);
            }
            _ if arg.starts_with("--bootstrap-peer=") => {
                if let Some(value) = arg.split_once('=').map(|(_, value)| value) {
                    overrides
                        .bootstrap_peers
                        .extend(parse_bootstrap_peer(value));
                }
            }
            _ if arg.starts_with("--bootstrap-peers=") => {
                if let Some(value) = arg.split_once('=').map(|(_, value)| value) {
                    overrides
                        .bootstrap_peers
                        .extend(parse_bootstrap_peer(value));
                }
            }
            _ if arg.starts_with("--api-port=") => {
                if let Some(value) = arg.split_once('=').map(|(_, value)| value) {
                    overrides.api_port = value.parse::<u16>().ok();
                }
            }
            _ if arg.starts_with("--p2p-bind=") => {
                if let Some(value) = arg.split_once('=').map(|(_, value)| value) {
                    overrides.p2p_bind = value.parse().ok();
                }
            }
            _ if arg.starts_with("--p2p-port=") => {
                if let Some(value) = arg.split_once('=').map(|(_, value)| value) {
                    overrides.p2p_port = value.parse::<u16>().ok();
                }
            }
            _ if arg.starts_with("--data-dir=") => {
                if let Some(value) = arg.split_once('=').map(|(_, value)| value) {
                    overrides.data_dir = Some(PathBuf::from(value));
                }
            }
            _ if arg.starts_with("--dispatcher-seed=") => {
                if let Some(value) = arg.split_once('=').map(|(_, value)| value) {
                    overrides.dispatcher_seed = value.parse::<u64>().ok();
                }
            }
            _ => {}
        }
    }

    overrides
}

pub(crate) fn read_bootstrap_peers_from_env() -> Vec<Multiaddr> {
    env::var("SILICIUM_BOOTSTRAP_PEERS")
        .ok()
        .map(|value| parse_bootstrap_peer(&value))
        .unwrap_or_default()
}

pub(crate) fn read_data_dir_from_env() -> PathBuf {
    env::var("SILICIUM_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/data"))
}

pub(crate) fn read_api_port_from_env() -> u16 {
    env::var("API_PORT")
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .unwrap_or(9092)
}

pub(crate) fn read_p2p_bind_from_env() -> std::net::IpAddr {
    env::var("SILICIUM_P2P_BIND")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or_else(|| std::net::IpAddr::from([0, 0, 0, 0]))
}

pub(crate) fn read_p2p_port_from_env() -> u16 {
    env::var("SILICIUM_P2P_PORT")
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .unwrap_or(0)
}

pub(crate) fn read_dispatcher_seed_from_env() -> u64 {
    env::var("SILICIUM_DISPATCH_SEED")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(7)
}

/// Work directory shared with the compute daemon (`SILICIUM_COMPUTE_ROOT`,
/// else `$SILICIUM_DATA_DIR/work`, else `./work`, like the daemon).
pub(crate) fn read_compute_root_from_env() -> PathBuf {
    env::var("SILICIUM_COMPUTE_ROOT")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
        .or_else(|| {
            env::var("SILICIUM_DATA_DIR")
                .ok()
                .map(|dir| PathBuf::from(dir).join("work"))
        })
        .unwrap_or_else(|| PathBuf::from("work"))
}

/// Whether a lone compute/verification peer may verify its own result
/// (`SILICIUM_ALLOW_SELF_VERIFICATION`, default on). Control-plane peers such
/// as the orchestrator do not prevent this fallback.
pub(crate) fn read_allow_self_verification_from_env() -> bool {
    !matches!(
        env::var("SILICIUM_ALLOW_SELF_VERIFICATION")
            .ok()
            .as_deref()
            .map(str::trim),
        Some("0" | "false" | "no" | "off")
    )
}

/// Approvals required on the tasks this node publishes
/// (`SILICIUM_VERIFICATIONS_REQUIRED`, default 1; 0 finalizes results
/// without cross-verification, e.g. on a single-node test network).
pub(crate) fn read_verifications_required_from_env() -> u32 {
    env::var("SILICIUM_VERIFICATIONS_REQUIRED")
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(1)
        .min(16)
}

/// Tasks computed at the same time (`SILICIUM_PARALLEL_TASKS`, default 1):
/// a node only claims a fragment when a slot is free.
pub(crate) fn read_parallel_tasks_from_env() -> usize {
    env::var("SILICIUM_PARALLEL_TASKS")
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(1)
        .clamp(1, 64)
}

/// Whether this node also computes the tasks it publishes
/// (`SILICIUM_WORK_OWN_TASKS`, default on; off for a publisher without a
/// compute daemon).
pub(crate) fn read_work_own_tasks_from_env() -> bool {
    !matches!(
        env::var("SILICIUM_WORK_OWN_TASKS")
            .ok()
            .as_deref()
            .map(str::trim),
        Some("0" | "false" | "no" | "off")
    )
}

pub(crate) fn read_enable_quic_listener_from_env() -> bool {
    env::var("SILICIUM_ENABLE_QUIC_LISTENER")
        .ok()
        .as_deref()
        .map(|value| value != "0")
        .unwrap_or(true)
}

pub(crate) fn merge_bootstrap_peers(
    mut bootstrap_peers: Vec<Multiaddr>,
    additional_peers: Vec<Multiaddr>,
) -> Vec<Multiaddr> {
    bootstrap_peers.extend(additional_peers);
    bootstrap_peers.sort_by_key(|addr| addr.to_string());
    bootstrap_peers.dedup_by(|left, right| left.to_string() == right.to_string());
    bootstrap_peers
}

impl NodeConfig {
    pub(crate) fn from_env_and_args() -> Self {
        let overrides = parse_node_cli_args(env::args().skip(1));
        let bootstrap_peers =
            merge_bootstrap_peers(read_bootstrap_peers_from_env(), overrides.bootstrap_peers);
        let mut trusted_publishers = overrides.trusted_publishers;
        trusted_publishers.extend(bootstrap_peer_ids(&bootstrap_peers));

        Self {
            bootstrap_peers,
            data_dir: overrides.data_dir.unwrap_or_else(read_data_dir_from_env),
            api_port: overrides.api_port.unwrap_or_else(read_api_port_from_env),
            p2p_bind: overrides.p2p_bind.unwrap_or_else(read_p2p_bind_from_env),
            p2p_port: overrides.p2p_port.unwrap_or_else(read_p2p_port_from_env),
            enable_quic_listener: overrides
                .enable_quic_listener
                .unwrap_or_else(read_enable_quic_listener_from_env),
            dispatcher_seed: overrides
                .dispatcher_seed
                .unwrap_or_else(read_dispatcher_seed_from_env),
            security: SecurityConfig::from_env(trusted_publishers),
        }
    }
}

pub(crate) fn default_hardware_profile() -> HardwareBucket {
    let profile = HardwareProfile::new(
        VramClass::Vram4096,
        GpuAcceleration {
            cuda: false,
            metal: false,
            rocm: false,
            vulkan: false,
            opencl: false,
        },
        SimdWidth::Avx2,
        OperatingSystem::Linux,
    );
    HardwareBucket::from_profile(profile)
}

pub(crate) fn read_hardware_bucket() -> HardwareBucket {
    env::var("SILICIUM_HW_BUCKET")
        .ok()
        .and_then(|raw| raw.parse::<u32>().ok())
        .map(HardwareBucket::new)
        .unwrap_or_else(default_hardware_profile)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Mutex, OnceLock};

    fn env_lock() -> std::sync::MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
            .lock()
            .expect("env test lock")
    }

    #[test]
    fn bootstrap_peers_with_a_pinned_id_are_trusted_publishers() {
        let orchestrator = PeerId::random();
        let addresses = parse_bootstrap_peer(&format!(
            "/ip4/10.77.0.1/tcp/46201/p2p/{orchestrator},/ip4/10.77.0.2/tcp/46201"
        ));
        assert_eq!(addresses.len(), 2);
        assert_eq!(bootstrap_peer_ids(&addresses), vec![orchestrator]);
    }

    #[test]
    fn parse_bootstrap_peer_filters_invalid_entries() {
        let peers = parse_bootstrap_peer(
            "/ip4/127.0.0.1/tcp/4001,not-a-multiaddr,/ip4/127.0.0.1/udp/4002/quic-v1",
        );
        assert_eq!(peers.len(), 2);
        assert!(
            peers
                .iter()
                .any(|addr| addr.to_string() == "/ip4/127.0.0.1/tcp/4001")
        );
        assert!(
            peers
                .iter()
                .any(|addr| addr.to_string() == "/ip4/127.0.0.1/udp/4002/quic-v1")
        );
    }

    #[test]
    fn merge_bootstrap_peers_sorts_and_deduplicates() {
        let first = vec![
            "/ip4/127.0.0.1/tcp/4002".parse().expect("addr"),
            "/ip4/127.0.0.1/tcp/4001".parse().expect("addr"),
        ];
        let second = vec![
            "/ip4/127.0.0.1/tcp/4001".parse().expect("addr"),
            "/ip4/127.0.0.1/tcp/4003".parse().expect("addr"),
        ];

        let merged = merge_bootstrap_peers(first, second)
            .into_iter()
            .map(|addr| addr.to_string())
            .collect::<Vec<_>>();
        assert_eq!(
            merged,
            vec![
                "/ip4/127.0.0.1/tcp/4001".to_string(),
                "/ip4/127.0.0.1/tcp/4002".to_string(),
                "/ip4/127.0.0.1/tcp/4003".to_string(),
            ]
        );
    }

    #[test]
    fn read_enable_quic_listener_from_env_accepts_zero_as_false() {
        let _guard = env_lock();
        let original = std::env::var("SILICIUM_ENABLE_QUIC_LISTENER").ok();

        // Rust 2024 marks environment mutation as unsafe because it is
        // process-global; the test lock keeps this deterministic.
        unsafe { std::env::set_var("SILICIUM_ENABLE_QUIC_LISTENER", "0") };
        assert!(!read_enable_quic_listener_from_env());

        unsafe { std::env::set_var("SILICIUM_ENABLE_QUIC_LISTENER", "1") };
        assert!(read_enable_quic_listener_from_env());

        match original {
            Some(value) => unsafe { std::env::set_var("SILICIUM_ENABLE_QUIC_LISTENER", value) },
            None => unsafe { std::env::remove_var("SILICIUM_ENABLE_QUIC_LISTENER") },
        }
    }

    #[test]
    fn parse_node_cli_args_supports_aliases_and_flags() {
        let overrides = parse_node_cli_args(vec![
            "--bootstrap-peer".to_string(),
            "/ip4/127.0.0.1/tcp/4001".to_string(),
            "--bootstrap-peers=/ip4/127.0.0.1/tcp/4002,/ip4/127.0.0.1/tcp/4003".to_string(),
            "--api-port=1337".to_string(),
            "--data-dir".to_string(),
            "C:/tmp/silicium".to_string(),
            "--dispatcher-seed".to_string(),
            "42".to_string(),
            "--disable-quic".to_string(),
        ]);

        assert_eq!(overrides.bootstrap_peers.len(), 3);
        assert_eq!(overrides.api_port, Some(1337));
        assert_eq!(overrides.data_dir, Some(PathBuf::from("C:/tmp/silicium")));
        assert_eq!(overrides.dispatcher_seed, Some(42));
        assert_eq!(overrides.enable_quic_listener, Some(false));
    }
}
