//! Constants and persisted node configuration: node id, orchestrator URL,
//! and the service configuration file read by the supervisor.

use crate::*;

pub(crate) const SUPERVISOR_TASK_NAME: &str = "SiliciumNodeService";

pub(crate) const SUPERVISOR_RUN_KEY_NAME: &str = "SiliciumNodeService";

pub(crate) const PROD_ORCHESTRATOR_URL: &str = "https://vps-910c1dbc.vps.ovh.net/orchestrator";
pub(crate) const PROD_API_BASE_URL: &str = "https://vps-910c1dbc.vps.ovh.net/api";
pub(crate) const DEV_API_BASE_URL: &str = "https://10.77.0.1:8443/api";

/// Dev channel orchestrator, reachable through the WireGuard VPN
/// (`public_base_url` of the dev channel in deploy/release/channels.json).
pub(crate) const DEV_ORCHESTRATOR_URL: &str = "https://10.77.0.1:8443/orchestrator";

/// Orchestrator of the network this build belongs to: a dev build joins the
/// dev network, a prod build the prod network. `SILICIUM_DEFAULT_ORCHESTRATOR_URL`
/// at build time overrides it.
pub(crate) fn default_orchestrator_url() -> &'static str {
    match option_env!("SILICIUM_DEFAULT_ORCHESTRATOR_URL") {
        Some(url) if !url.trim().is_empty() => url,
        _ if release_channel() == "prod" => PROD_ORCHESTRATOR_URL,
        _ => DEV_ORCHESTRATOR_URL,
    }
}

pub(crate) fn default_api_base_url() -> &'static str {
    match option_env!("SILICIUM_DEFAULT_API_BASE_URL") {
        Some(url) if !url.trim().is_empty() => url,
        _ if release_channel() == "prod" => PROD_API_BASE_URL,
        _ => DEV_API_BASE_URL,
    }
}

/// libp2p rendezvous of the dev orchestrator, through the WireGuard VPN. It
/// ends with the orchestrator's peer id (`Local peer id` in its log), derived
/// from `identity.key` in its state directory on the VPS: if that file is
/// lost, the orchestrator gets a new id and dev builds must be rebuilt with it.
pub(crate) const DEV_NODE_BOOTSTRAP_PEERS: &str =
    "/ip4/10.77.0.1/tcp/46201/p2p/12D3KooWPCXXi9DUqqao5bcjt7yT3xJyx1gsUSRyNWCKp218ioon";

/// Prod rendezvous. Not pinned yet: add `/p2p/<prod peer id>` before the prod
/// network switches to the Rust node, or prod nodes will ignore its tasks.
pub(crate) const PROD_NODE_BOOTSTRAP_PEERS: &str = "/dns4/vps-910c1dbc.vps.ovh.net/tcp/46101";

/// Direct libp2p rendezvous used by the Rust node. The HTTPS orchestrator URL
/// remains the public control-plane address, while the Rust runtime joins the
/// peer mesh through a multiaddr.
///
/// A pinned peer id (`/p2p/<peer id>`) makes the connection fail if another
/// identity answers, and makes that peer the node's only trusted publisher:
/// the node executes no task signed by anyone else.
/// `SILICIUM_DEFAULT_BOOTSTRAP_PEERS` at build time overrides it.
pub(crate) fn default_node_bootstrap_peers() -> &'static str {
    match option_env!("SILICIUM_DEFAULT_BOOTSTRAP_PEERS") {
        Some(peers) if !peers.trim().is_empty() => peers,
        _ if release_channel() == "prod" => PROD_NODE_BOOTSTRAP_PEERS,
        _ => DEV_NODE_BOOTSTRAP_PEERS,
    }
}

// NAT/ICE discovery and the first scheduler poll can legitimately take longer
// than a short watchdog interval.  Restarting during that bootstrap period
// prevents a node from ever becoming available to claim work.
pub(crate) const CLAIM_POLL_STALE_AFTER: Duration = Duration::from_secs(90);

pub(crate) const NODE_READY_TIMEOUT: Duration = Duration::from_secs(45);

pub(crate) const UPDATE_SIGNING_PUBLIC_KEY_B64: &str =
    "px9didtoGftLilUX8iA1Yoj4PjNiCvZD47GK6/fdzX8=";

pub(crate) const UPDATE_SIGNING_KEY_ID: &str =
    "f8d1c0149d9fcc171a39f96e5b9965a235500b7fe20cd2348912d38ca91e6d4c";

pub(crate) fn normalized_node_id(node_id: &str) -> String {
    let normalized = node_id
        .trim()
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.') {
                character
            } else {
                '-'
            }
        })
        .collect::<String>()
        .trim_matches('-')
        .chars()
        .take(64)
        .collect::<String>();
    if normalized.is_empty() {
        "silicium-desktop-node".to_string()
    } else {
        normalized
    }
}

pub(crate) fn effective_node_id(node_id: &str) -> String {
    let normalized = normalized_node_id(node_id);
    if normalized == "silicium-desktop-node" {
        persistent_node_id()
    } else {
        normalized
    }
}

pub(crate) fn persistent_node_id() -> String {
    let path = app_state_dir().join("node-id.txt");
    if let Ok(saved) = fs::read_to_string(&path) {
        let normalized = normalized_node_id(&saved);
        if normalized != "silicium-desktop-node" {
            return normalized;
        }
    }

    let machine = env::var("COMPUTERNAME")
        .or_else(|_| env::var("HOSTNAME"))
        .unwrap_or_else(|_| "desktop".to_string());
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let generated = normalized_node_id(&format!("silicium-{machine}-{nonce:x}"));
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = fs::write(path, &generated);
    generated
}

pub(crate) fn normalize_orchestrator_url(value: &str) -> Result<String, String> {
    let migrated = migrate_legacy_orchestrator_url(value);
    let trimmed = migrated.trim().trim_end_matches('/');
    if trimmed.is_empty() {
        return Err("orchestrator_url_missing".to_string());
    }
    if !(trimmed.starts_with("http://") || trimmed.starts_with("https://")) {
        return Err("orchestrator_url_invalid_scheme".to_string());
    }
    let authority = trimmed
        .split_once("://")
        .map(|(_, rest)| rest)
        .unwrap_or_default()
        .split('/')
        .next()
        .unwrap_or_default();
    if authority.is_empty() || authority.contains(char::is_whitespace) {
        return Err("orchestrator_url_invalid_host".to_string());
    }
    Ok(trimmed.to_string())
}

pub(crate) fn migrate_legacy_orchestrator_url(value: &str) -> String {
    let trimmed = value.trim().trim_end_matches('/');
    let lower = trimmed.to_ascii_lowercase();
    let legacy_hosts = [
        "http://213.32.68.67:46100",
        "https://213.32.68.67:46100",
        "http://vps-910c1dbc.vps.ovh.net:46100",
        "https://vps-910c1dbc.vps.ovh.net:46100",
        "http://silicium.example.com:46100",
        "https://silicium.example.com:46100",
    ];
    if legacy_hosts
        .iter()
        .any(|host| lower == *host || lower == format!("{host}/orchestrator"))
    {
        return default_orchestrator_url().to_string();
    }
    // Prod and dev installs share the same app data directory, so a saved
    // configuration may hold the other channel's default: follow this build.
    let channel_defaults = [PROD_ORCHESTRATOR_URL, DEV_ORCHESTRATOR_URL];
    if channel_defaults
        .iter()
        .any(|default| lower == default.to_ascii_lowercase())
    {
        return default_orchestrator_url().to_string();
    }
    trimmed.to_string()
}

pub(crate) fn write_service_config(repo_root: &Path, config: &NodeConfig) -> Result<(), String> {
    let path = service_config_path(repo_root);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let content = format!(
        "repo_root={}\norchestrator_url={}\nadvertise_host={}\nnode_id={}\nreputation_score={}\n",
        repo_root.display(),
        config.orchestrator_url,
        config.advertise_host,
        config.node_id,
        config.reputation_score
    );
    fs::write(path, content).map_err(|error| error.to_string())?;
    write_global_repo_root(repo_root)
}

pub(crate) fn read_service_config(repo_root: &Path) -> Result<NodeConfig, String> {
    let content =
        fs::read_to_string(service_config_path(repo_root)).map_err(|error| error.to_string())?;
    let mut config = NodeConfig {
        repo_root: repo_root.display().to_string(),
        orchestrator_url: default_orchestrator_url().to_string(),
        advertise_host: String::new(),
        node_id: "silicium-desktop-node".to_string(),
        reputation_score: 100,
    };
    for line in content.lines() {
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        match key {
            "repo_root" => config.repo_root = value.to_string(),
            "orchestrator_url" => config.orchestrator_url = value.to_string(),
            "advertise_host" => config.advertise_host = value.to_string(),
            "node_id" => config.node_id = value.to_string(),
            "reputation_score" => {
                config.reputation_score = value.parse::<u16>().unwrap_or(config.reputation_score);
            }
            _ => {}
        }
    }
    config.orchestrator_url = migrate_legacy_orchestrator_url(&config.orchestrator_url);
    Ok(config)
}
