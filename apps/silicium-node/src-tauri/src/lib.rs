use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use chrono::{DateTime, SecondsFormat, Utc};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    cmp::Ordering,
    env,
    ffi::OsStr,
    fs::{self, OpenOptions},
    io::{Read, Write},
    net::{TcpListener, TcpStream, UdpSocket},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::State;

#[cfg(target_os = "windows")]
mod tray;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
use windows_sys::Win32::{
    Foundation::{CloseHandle, STILL_ACTIVE},
    System::Threading::{GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION},
};

#[derive(Default)]
struct ProcessState {
    node: Mutex<Option<Child>>,
}

const SUPERVISOR_TASK_NAME: &str = "SiliciumNodeService";
const SUPERVISOR_RUN_KEY_NAME: &str = "SiliciumNodeService";
const DEFAULT_ORCHESTRATOR_URL: &str = "https://vps-910c1dbc.vps.ovh.net/orchestrator";
// NAT/ICE discovery and the first scheduler poll can legitimately take longer
// than a short watchdog interval.  Restarting during that bootstrap period
// prevents a node from ever becoming available to claim work.
const CLAIM_POLL_STALE_AFTER: Duration = Duration::from_secs(90);
const NODE_READY_TIMEOUT: Duration = Duration::from_secs(45);
const UPDATE_SIGNING_PUBLIC_KEY_B64: &str = "px9didtoGftLilUX8iA1Yoj4PjNiCvZD47GK6/fdzX8=";
const UPDATE_SIGNING_KEY_ID: &str =
    "f8d1c0149d9fcc171a39f96e5b9965a235500b7fe20cd2348912d38ca91e6d4c";
const LOCAL_UPDATE_MANIFEST_URL: &str = "http://127.0.0.1:46101/updates/manifest";

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct NodeConfig {
    repo_root: String,
    orchestrator_url: String,
    advertise_host: String,
    node_id: String,
    reputation_score: u16,
}

#[derive(Debug, Serialize)]
struct NodeStatus {
    running: bool,
    roles: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct AppDefaults {
    repo_root: String,
    advertise_host: String,
    orchestrator_url: String,
    node_id: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct CheckItem {
    name: String,
    ok: bool,
    detail: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct NodeActivity {
    known_results: usize,
    known_tasks: usize,
    last_result: String,
    storage_bytes: u64,
    history: Vec<HistoryItem>,
    machines: Vec<MachineActivity>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct MachineActivity {
    node_id: String,
    identity_id: String,
    online: bool,
    self_node: bool,
    scheduler_active: bool,
    status: String,
    roles: Vec<String>,
    app_version: String,
    release_channel: String,
    release_build: String,
    http_base_url: String,
    mesh_post_url: String,
    relay_capable: bool,
    features: Vec<String>,
    candidates: Vec<MachineCandidate>,
    transport_attestations: Vec<TransportAttestation>,
    platform: String,
    cpu_count: u64,
    telemetry: RuntimeTelemetry,
    resource_reputation: Vec<BayesianResourceScore>,
    active_tasks: Vec<MachineTaskActivity>,
    task_queue: Vec<MachineQueueItem>,
    last_seen_unix: u64,
    last_seen_utc: String,
    last_claim_poll_utc: String,
    last_claim_error: String,
    last_response_ok: Option<bool>,
    last_response_item_id: String,
    last_response_utc: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct MachineCandidate {
    candidate_type: String,
    transport: String,
    ip: String,
    port: u64,
    internet_routable: bool,
    source: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct TransportAttestation {
    claim_hash: String,
    signature: String,
    route: String,
    transport_backend: String,
    proof_scope: String,
    remote_peer_id: String,
    session_id: String,
    task_id: String,
    content_id: String,
    size_bytes: u64,
    endpoint: String,
    relay_peer_id: String,
    peer_proof_verified: bool,
    success: bool,
    failure_reason: String,
    timestamp_unix: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct MachineTaskActivity {
    item_id: String,
    role: String,
    activity: String,
    workload: String,
    fragment_index: String,
    fragment_count: String,
    source_task_id: String,
    source_node_id: String,
    bounds: String,
    phase: String,
    progress_percent: f64,
    progress_source: String,
    elapsed_ms: u64,
    eta_seconds: f64,
    completed_units: f64,
    total_units: f64,
    unit: String,
    throughput_units_per_second: f64,
    worker_threads: u64,
    pixels_completed: u64,
    pixels_total: u64,
    input_bytes: u64,
    attempt: u64,
    max_retries: u64,
    priority: String,
    queued_utc: String,
    resource_usage: RuntimeTelemetry,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct MachineQueueItem {
    item_id: String,
    kind: String,
    role: String,
    activity: String,
    workload: String,
    fragment_index: String,
    fragment_count: String,
    source_task_id: String,
    source_node_id: String,
    status: String,
    priority: String,
    assigned_peer_id: String,
    origin_node_id: String,
    bounds: String,
    queued_utc: String,
}

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeTelemetry {
    sampled_unix: u64,
    sample_interval_ms: u64,
    node_uptime_seconds: f64,
    process_cpu_percent: f64,
    process_cpu_percent_one_core: f64,
    process_cpu_seconds: f64,
    process_rss_bytes: u64,
    process_peak_rss_bytes: u64,
    system_cpu_percent: f64,
    system_memory_total_bytes: u64,
    system_memory_available_bytes: u64,
    system_memory_used_bytes: u64,
    system_memory_percent: f64,
    logical_cpu_count: u64,
    python_thread_count: u64,
    load_average: Vec<f64>,
    storage_total_bytes: u64,
    storage_free_bytes: u64,
    storage_used_percent: f64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct NodeDiagnostics {
    repo_root: String,
    silicium_cli: String,
    log_dir: String,
    node_pid: Option<u32>,
    supervisor_pid: Option<u32>,
    node_running: bool,
    supervisor_running: bool,
    port_ready: bool,
    orchestrator: CheckItem,
    openssl: CheckItem,
    python: CheckItem,
    log_tail: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct HistoryItem {
    name: String,
    modified_at: u64,
    size_bytes: u64,
    kind: String,
    item_id: String,
    role: String,
    activity: String,
    fragment_index: String,
    ok: Option<bool>,
    peer_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct UpdateStatus {
    current_version: String,
    current_channel: String,
    current_build: String,
    latest_version: String,
    #[serde(default)]
    latest_build: String,
    #[serde(default)]
    latest_content_id: String,
    state: String,
    update_available: bool,
    automatic: bool,
    last_checked_utc: String,
    error: String,
    check_interval_seconds: u64,
}

#[derive(Debug, Clone, Deserialize)]
struct UpdateRelease {
    version: String,
    #[serde(default)]
    build: String,
    #[serde(default)]
    channel: String,
    #[serde(default)]
    platform: String,
    url: String,
    sha256: String,
    #[serde(default)]
    content_id: String,
    #[serde(default)]
    signature: String,
    #[serde(default)]
    signing_key_id: String,
    #[serde(default)]
    size_bytes: u64,
    #[serde(default = "default_true")]
    auto_install: bool,
    #[serde(default)]
    check_interval_seconds: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct UpdateInstallFailure {
    content_id: String,
    version: String,
    build: String,
    error: String,
    failed_at_utc: String,
}

#[tauri::command]
fn node_status(
    repo_root: Option<String>,
    state: State<ProcessState>,
) -> Result<NodeStatus, String> {
    let mut node = state
        .node
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    if let Some(child) = node.as_mut() {
        match child.try_wait().map_err(|error| error.to_string())? {
            None => {
                return Ok(NodeStatus {
                    running: true,
                    roles: "compute,verify".to_string(),
                });
            }
            Some(_) => {
                *node = None;
            }
        }
    }

    let root = resolve_optional_repo_root(repo_root.as_deref());
    if let Some(root) = root.as_ref() {
        cleanup_dead_pids(root);
    }
    let node_running = root
        .as_ref()
        .and_then(|root| read_pid(root).ok().flatten())
        .map(process_is_running)
        .unwrap_or(false);
    let node_ready = root.is_some() && local_network_node_ready(46101);
    let running = node_ready;
    if !node_running {
        if let Some(root) = root.as_ref() {
            remove_pid(root);
        }
    }

    Ok(NodeStatus {
        running,
        roles: "compute,verify".to_string(),
    })
}

#[tauri::command]
fn start_node(mut config: NodeConfig, state: State<ProcessState>) -> Result<String, String> {
    let mut node = state
        .node
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    if node.is_some() {
        return Ok("Silicium node already running".to_string());
    }

    config.node_id = effective_node_id(&config.node_id);
    config.orchestrator_url = migrate_legacy_orchestrator_url(&config.orchestrator_url);
    config.orchestrator_url = normalize_orchestrator_url(&config.orchestrator_url)?;
    let repo_root = resolve_repo_root(&config.repo_root)?;
    validate_repo_root(&repo_root)?;
    cleanup_dead_pids(&repo_root);
    if local_network_node_ready(46101) {
        return Ok("Silicium node already running in background".to_string());
    }
    let managed_process_starting = read_supervisor_pid(&repo_root)?
        .map(process_is_running)
        .unwrap_or(false)
        || read_pid(&repo_root)?.map(process_is_running).unwrap_or(false);
    if managed_process_starting && wait_for_existing_node_start(&repo_root, 46101) {
        return Ok("Silicium local service already running".to_string());
    }
    cleanup_previous_node_processes(&repo_root);
    cleanup_dead_pids(&repo_root);
    if let Some(pid) = read_supervisor_pid(&repo_root)? {
        if process_is_running(pid) {
            return Ok("Silicium local service already running".to_string());
        }
        remove_supervisor_pid(&repo_root);
    }
    if let Some(pid) = read_pid(&repo_root)? {
        if process_is_running(pid) {
            return Ok("Silicium node already running in background".to_string());
        }
        remove_pid(&repo_root);
    }

    write_service_config(&repo_root, &config)?;
    let autostart_warning = match install_autostart_task(&repo_root) {
        Ok(()) => None,
        Err(error) => {
            let _ = append_supervisor_log(
                &repo_root,
                &format!("autostart_task_install_failed: {error}\n"),
            );
            Some(error)
        }
    };
    let mut child = spawn_supervisor(&repo_root)?;
    wait_for_supervised_node_start(&mut child, &repo_root, 46101)?;
    drop(child);
    *node = None;
    if let Some(warning) = autostart_warning {
        Ok(format!(
            "Silicium node started, but autostart is not installed yet: {warning}"
        ))
    } else {
        Ok(format!(
            "Silicium local service started with compute,verify roles against {}",
            config.orchestrator_url
        ))
    }
}

#[cfg(target_os = "windows")]
fn start_configured_node_service() -> Result<String, String> {
    let repo_root = resolve_repo_root_readonly("")?;
    validate_repo_root(&repo_root)?;
    read_service_config(&repo_root).map_err(|_| "node_not_configured".to_string())?;
    install_autostart_task(&repo_root)?;
    cleanup_dead_pids(&repo_root);

    if read_supervisor_pid(&repo_root)?
        .map(process_is_running)
        .unwrap_or(false)
    {
        if wait_for_existing_node_start(&repo_root, 46101) {
            return Ok("Le service Silicium est deja demarre.".to_string());
        }
        cleanup_previous_node_processes(&repo_root);
    }

    let mut child = spawn_supervisor(&repo_root)?;
    wait_for_supervised_node_start(&mut child, &repo_root, 46101)?;
    drop(child);
    Ok("Le service Silicium est demarre.".to_string())
}

#[cfg(target_os = "windows")]
fn migrate_configured_node_autostart() -> Result<(), String> {
    let repo_root = resolve_repo_root_readonly("")?;
    validate_repo_root(&repo_root)?;
    read_service_config(&repo_root).map_err(|_| "node_not_configured".to_string())?;
    install_autostart_task(&repo_root)
}

#[cfg(target_os = "windows")]
fn stop_configured_node_service() -> Result<String, String> {
    let repo_root = resolve_repo_root_readonly("")?;
    stop_node_processes(&repo_root)?;
    Ok("Le service Silicium est arrete jusqu'au prochain demarrage manuel.".to_string())
}

#[cfg(target_os = "windows")]
fn restart_configured_node_service() -> Result<String, String> {
    let repo_root = resolve_repo_root_readonly("")?;
    read_service_config(&repo_root).map_err(|_| "node_not_configured".to_string())?;
    stop_node_processes(&repo_root)?;
    thread::sleep(Duration::from_millis(500));
    start_configured_node_service()?;
    Ok("Le service Silicium a ete redemarre.".to_string())
}

#[cfg(target_os = "windows")]
fn configured_node_service_running() -> bool {
    let Some(repo_root) = resolve_optional_repo_root(None) else {
        return false;
    };
    cleanup_dead_pids(&repo_root);
    local_network_node_ready(46101)
}

#[tauri::command]
fn stop_node(repo_root: Option<String>, state: State<ProcessState>) -> Result<String, String> {
    let mut node = state
        .node
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    if let Some(mut child) = node.take() {
        let _ = child.kill();
    }

    let root = resolve_optional_repo_root(repo_root.as_deref());
    if let Some(root) = root {
        cleanup_node_installation(&root)?;
    } else {
        kill_known_silicium_processes(None);
        uninstall_autostart_task();
        remove_global_repo_root();
    }

    Ok("Silicium local service stopped".to_string())
}

#[tauri::command]
fn check_environment(repo_root: String) -> Result<Vec<CheckItem>, String> {
    let root = resolve_repo_root(&repo_root)?;
    let mut checks = vec![
        python_command_check(&root),
        identity_mode_check(),
    ];

    checks.push(path_check("Repo Silicium", &root.join("Network")));
    checks.push(path_check(
        "Raytracer runtime",
        &root.join(".silicium").join("env").join("raytracer.env"),
    ));
    Ok(checks)
}

#[tauri::command]
fn install_runtime(repo_root: String) -> Result<String, String> {
    let root = resolve_repo_root(&repo_root)?;
    validate_repo_root(&root)?;
    let status = if cfg!(target_os = "windows") {
        let script = root.join("install-silicium-windows.cmd");
        if !script.exists() {
            return Err(format!("installer_not_found: {}", script.display()));
        }
        let mut command = Command::new("cmd");
        command
            .arg("/C")
            .arg(script)
            .arg("-SkipDockerCheck")
            .current_dir(&root)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        configure_detached_process(&mut command);
        command.status()
    } else if cfg!(target_os = "linux") {
        let mut command = Command::new(python_launcher(&root));
        command
            .arg("-c")
            .arg("import aioice, cryptography")
            .current_dir(&root)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        apply_runtime_path(&mut command, &root);
        configure_python_command(&mut command, &root);
        command.status()
    } else {
        return Err(format!("runtime_install_unsupported:{}", env::consts::OS));
    };
    let status = status.map_err(|error| error.to_string())?;
    if !status.success() {
        return Err(format!("installer_failed: {status}"));
    }
    Ok("Runtime pret".to_string())
}

#[tauri::command]
fn node_activity(repo_root: String) -> Result<NodeActivity, String> {
    let root = resolve_repo_root_readonly(&repo_root)?;
    validate_repo_root(&root)?;
    let networked_dir = root
        .join("Network")
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node");
    let mut history = Vec::new();
    collect_event_history(
        &networked_dir.join("export").join("node.events.ndjson"),
        &mut history,
    );
    collect_history(&networked_dir, &mut history);
    history.sort_by(|left, right| right.modified_at.cmp(&left.modified_at));
    history
        .dedup_by(|left, right| left.name == right.name && left.modified_at == right.modified_at);
    let known_results = history
        .iter()
        .filter(|item| item.name.starts_with("result."))
        .count();
    let known_tasks = history
        .iter()
        .filter(|item| item.name.contains("task") || item.name.contains("queue"))
        .count();
    let last_result = history
        .iter()
        .find(|item| item.name.starts_with("result."))
        .map(|item| item.name.clone())
        .unwrap_or_else(|| "Aucun resultat local pour le moment".to_string());
    history.truncate(50);
    let storage_bytes = directory_size(&networked_dir);
    let machines = collect_machine_activity(&networked_dir.join("export"));

    Ok(NodeActivity {
        known_results,
        known_tasks,
        last_result,
        storage_bytes,
        history,
        machines,
    })
}

#[tauri::command]
fn node_diagnostics(repo_root: String) -> Result<NodeDiagnostics, String> {
    let root = resolve_repo_root_readonly(&repo_root)?;
    validate_repo_root(&root)?;
    cleanup_dead_pids(&root);
    let node_pid = read_pid(&root).ok().flatten();
    let supervisor_pid = read_supervisor_pid(&root).ok().flatten();
    let node_running = node_pid.map(process_is_running).unwrap_or(false);
    let supervisor_running = supervisor_pid.map(process_is_running).unwrap_or(false);
    let port_ready = local_network_node_ready(46101);
    let orchestrator_url = read_service_config(&root)
        .map(|config| config.orchestrator_url)
        .unwrap_or_else(|_| DEFAULT_ORCHESTRATOR_URL.to_string());
    let log_dir = node_app_log_path(&root, "silicium-node.err.log")
        .parent()
        .map(|path| path.display().to_string())
        .unwrap_or_else(|| root.display().to_string());
    let silicium_cli = root.join("Network").join("silicium");
    Ok(NodeDiagnostics {
        repo_root: root.display().to_string(),
        silicium_cli: silicium_cli.display().to_string(),
        log_dir,
        node_pid,
        supervisor_pid,
        node_running,
        supervisor_running,
        port_ready,
        orchestrator: orchestrator_check(&orchestrator_url),
        openssl: identity_mode_check(),
        python: python_command_check(&root),
        log_tail: read_node_log_tail(&root)
            .unwrap_or_else(|| "Aucun log node disponible pour le moment.".to_string()),
    })
}

#[tauri::command]
fn app_defaults() -> AppDefaults {
    let repo_root = ensure_packaged_runtime_preferred()
        .or_else(discover_managed_runtime_root)
        .map(|path| path.display().to_string())
        .unwrap_or_default();
    let saved_config =
        discover_managed_runtime_root().and_then(|root| read_service_config(&root).ok());
    AppDefaults {
        repo_root,
        advertise_host: detect_local_ip().unwrap_or_else(|| "127.0.0.1".to_string()),
        orchestrator_url: saved_config
            .as_ref()
            .map(|config| config.orchestrator_url.clone())
            .unwrap_or_else(|| DEFAULT_ORCHESTRATOR_URL.to_string()),
        node_id: saved_config
            .map(|config| effective_node_id(&config.node_id))
            .unwrap_or_else(persistent_node_id),
    }
}

#[tauri::command]
fn update_status() -> UpdateStatus {
    read_update_status().unwrap_or_else(default_update_status)
}

#[tauri::command]
fn check_for_updates() -> UpdateStatus {
    check_for_update_once(false)
}

fn default_true() -> bool {
    true
}

fn release_version() -> &'static str {
    option_env!("SILICIUM_RELEASE_VERSION").unwrap_or(env!("CARGO_PKG_VERSION"))
}

fn release_channel() -> &'static str {
    option_env!("SILICIUM_RELEASE_CHANNEL").unwrap_or(if env!("CARGO_PKG_VERSION").contains('-') {
        "dev"
    } else {
        "prod"
    })
}

fn release_build() -> &'static str {
    option_env!("SILICIUM_RELEASE_BUILD").unwrap_or("")
}

fn update_manifest_url() -> &'static str {
    option_env!("SILICIUM_UPDATE_MANIFEST_URL")
        .unwrap_or("https://vps-910c1dbc.vps.ovh.net/downloads/update-manifest.json")
}

fn default_update_interval() -> u64 {
    if release_channel() == "dev" {
        30
    } else {
        21_600
    }
}

fn default_update_status() -> UpdateStatus {
    UpdateStatus {
        current_version: release_version().to_string(),
        current_channel: release_channel().to_string(),
        current_build: release_build().to_string(),
        latest_version: String::new(),
        latest_build: String::new(),
        latest_content_id: String::new(),
        state: "unknown".to_string(),
        update_available: false,
        automatic: true,
        last_checked_utc: String::new(),
        error: String::new(),
        check_interval_seconds: default_update_interval(),
    }
}

fn update_status_path() -> PathBuf {
    app_state_dir().join("update-status.json")
}

fn update_lock_path() -> PathBuf {
    app_state_dir().join("update-check.lock")
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct BayesianResourceScore {
    dimension: String,
    mean: f64,
    lower_bound: f64,
    evidence: f64,
    short_term_mean: f64,
    long_term_mean: f64,
}

fn update_install_lock_path() -> PathBuf {
    app_state_dir().join("update-install.lock")
}

fn update_install_failure_path() -> PathBuf {
    app_state_dir().join("update-install-failure.json")
}

fn update_failure_retry_interval() -> u64 {
    // A failed artifact is blocked until the manifest publishes a different
    // content id. Keep the background loop quiet even on development builds.
    21_600
}

fn read_update_install_failure() -> Option<UpdateInstallFailure> {
    fs::read_to_string(update_install_failure_path())
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
}

fn write_update_install_failure(failure: &UpdateInstallFailure) {
    let path = update_install_failure_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(raw) = serde_json::to_vec_pretty(failure) {
        let _ = fs::write(path, raw);
    }
}

fn clear_update_install_failure() {
    let _ = fs::remove_file(update_install_failure_path());
}

fn update_install_failure_matches(failure: &UpdateInstallFailure, release: &UpdateRelease) -> bool {
    if !failure.content_id.trim().is_empty() && !release.content_id.trim().is_empty() {
        return failure.content_id.trim() == release.content_id.trim();
    }
    failure.version.trim() == release.version.trim() && failure.build.trim() == release.build.trim()
}

fn record_update_install_failure(release: &UpdateRelease, error: &str) {
    write_update_install_failure(&UpdateInstallFailure {
        content_id: release.content_id.clone(),
        version: release.version.clone(),
        build: release.build.clone(),
        error: error.to_string(),
        failed_at_utc: current_utc(),
    });
}

fn read_update_status() -> Option<UpdateStatus> {
    fs::read_to_string(update_status_path())
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
}

fn write_update_status(status: &UpdateStatus) {
    let path = update_status_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(raw) = serde_json::to_vec_pretty(status) {
        let _ = fs::write(path, raw);
    }
}

fn acquire_update_lock() -> bool {
    let path = update_lock_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(metadata) = fs::metadata(&path) {
        let stale = metadata
            .modified()
            .ok()
            .and_then(|time| time.elapsed().ok())
            .map(|age| age > Duration::from_secs(300))
            .unwrap_or(true);
        if stale {
            let _ = fs::remove_file(&path);
        }
    }
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .and_then(|mut file| {
            use std::io::Write;
            writeln!(file, "{}", std::process::id())
        })
        .is_ok()
}

fn release_update_lock() {
    let _ = fs::remove_file(update_lock_path());
}

fn acquire_update_install_lock(content_id: &str) -> Result<bool, String> {
    let path = update_install_lock_path();
    acquire_install_lock_at(&path, content_id, Duration::from_secs(30 * 60))
}

fn acquire_install_lock_at(
    path: &Path,
    content_id: &str,
    stale_after: Duration,
) -> Result<bool, String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    if let Ok(metadata) = fs::metadata(path) {
        let stale = metadata
            .modified()
            .ok()
            .and_then(|time| time.elapsed().ok())
            .map(|age| age > stale_after)
            .unwrap_or(true);
        if stale {
            let _ = fs::remove_file(path);
        }
    }
    match OpenOptions::new().write(true).create_new(true).open(path) {
        Ok(mut file) => {
            use std::io::Write;
            writeln!(file, "{content_id}").map_err(|error| error.to_string())?;
            Ok(true)
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => Ok(false),
        Err(error) => Err(error.to_string()),
    }
}

fn release_update_install_lock() {
    let _ = fs::remove_file(update_install_lock_path());
}

fn check_for_update_once(auto_install: bool) -> UpdateStatus {
    if !acquire_update_lock() {
        return read_update_status().unwrap_or_else(default_update_status);
    }
    let mut status = default_update_status();
    status.state = "checking".to_string();
    write_update_status(&status);
    let result = check_for_update_locked(&mut status, auto_install);
    if let Err(error) = result {
        status.state = "error".to_string();
        status.error = error;
        status.last_checked_utc = current_utc();
        write_update_status(&status);
    }
    release_update_lock();
    status
}

fn check_for_update_locked(status: &mut UpdateStatus, auto_install: bool) -> Result<(), String> {
    let release = fetch_update_release()?;
    status.latest_version = release.version.clone();
    status.latest_build = release.build.clone();
    status.latest_content_id = release.content_id.clone();
    status.check_interval_seconds = if release.check_interval_seconds > 0 {
        release.check_interval_seconds.max(15)
    } else {
        default_update_interval()
    };
    status.automatic = release.auto_install;
    status.last_checked_utc = current_utc();
    status.update_available = release_requires_update(
        &release.version,
        &release.build,
        release_version(),
        release_build(),
    );
    status.error.clear();
    if !status.update_available {
        clear_update_install_failure();
    } else if let Some(failure) = read_update_install_failure() {
        if update_install_failure_matches(&failure, &release) {
            status.state = "error".to_string();
            status.error = format!(
                "update_install_blocked:{}:{}",
                failure.error,
                failure.content_id
            );
            status.check_interval_seconds = update_failure_retry_interval();
            write_update_status(status);
            return Ok(());
        }
    }
    status.state = if status.update_available {
        "available"
    } else {
        "current"
    }
    .to_string();
    write_update_status(status);

    if auto_install && status.update_available && release.auto_install {
        if node_has_active_work() {
            status.state = "waiting_for_idle".to_string();
            write_update_status(status);
            return Ok(());
        }
        if !acquire_update_install_lock(&release.content_id)? {
            status.state = "installing".to_string();
            write_update_status(status);
            return Ok(());
        }
        status.state = "downloading".to_string();
        write_update_status(status);
        let installer = match download_update(&release) {
            Ok(installer) => installer,
            Err(error) => {
                record_update_install_failure(&release, &error);
                status.check_interval_seconds = update_failure_retry_interval();
                release_update_install_lock();
                return Err(error);
            }
        };
        status.state = "installing".to_string();
        write_update_status(status);
        if let Err(error) = schedule_update_install(&installer, &release) {
            record_update_install_failure(&release, &error);
            status.check_interval_seconds = update_failure_retry_interval();
            release_update_install_lock();
            return Err(error);
        }
    }
    Ok(())
}

fn node_has_active_work() -> bool {
    let Some(root) = discover_managed_runtime_root() else {
        return false;
    };
    let events_path = root
        .join("Network")
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node")
        .join("export")
        .join("node.events.ndjson");
    let Ok(raw) = fs::read_to_string(events_path) else {
        return false;
    };
    for line in raw.lines().rev().take(500) {
        let Ok(event) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        match event.get("kind").and_then(Value::as_str).unwrap_or("") {
            "task_started" => return true,
            "task" | "request" | "result_return" => return false,
            _ => {}
        }
    }
    false
}

fn fetch_update_release() -> Result<UpdateRelease, String> {
    let primary = curl_get(update_manifest_url(), 15)
        .and_then(|output| {
            serde_json::from_str::<Value>(output.trim())
                .map_err(|error| format!("update_manifest_invalid:{error}"))
        })
        .and_then(|manifest| select_update_release(&manifest));
    let primary_error = match primary {
        Ok(release) => return Ok(release),
        Err(error) => error,
    };
    let fallback = curl_get(LOCAL_UPDATE_MANIFEST_URL, 10)
        .and_then(|output| {
            serde_json::from_str::<Value>(output.trim())
                .map_err(|error| format!("update_gossip_manifest_invalid:{error}"))
        })
        .and_then(|manifest| select_update_release(&manifest));
    fallback.map_err(|fallback_error| {
        format!("update_manifest_unavailable:primary={primary_error};gossip={fallback_error}")
    })
}

fn select_update_release(manifest: &Value) -> Result<UpdateRelease, String> {
    let mut candidates = Vec::new();
    if let Some(channel) = manifest
        .get("channels")
        .and_then(Value::as_object)
        .and_then(|channels| channels.get(release_channel()))
    {
        candidates.push(channel.clone());
    }
    if let Some(releases) = manifest.get("releases").and_then(Value::as_array) {
        candidates.extend(releases.iter().cloned());
    }
    let mut valid = Vec::new();
    for candidate in candidates {
        let Ok(mut release) = serde_json::from_value::<UpdateRelease>(candidate) else {
            continue;
        };
        if release.channel.trim().is_empty() {
            release.channel = release_channel().to_string();
        }
        if release.channel != release_channel()
            || !update_platform_matches(&release.platform)
            || validate_update_release(&release).is_err()
        {
            continue;
        }
        valid.push(release);
    }
    valid
        .into_iter()
        .max_by(|left, right| compare_versions(&left.version, &right.version))
        .ok_or_else(|| format!("update_channel_missing_or_untrusted:{}", release_channel()))
}

fn update_platform() -> String {
    format!("{}-{}", env::consts::OS, env::consts::ARCH)
}

fn update_platform_matches(platform: &str) -> bool {
    let candidate = platform.trim().to_ascii_lowercase();
    if candidate.is_empty() {
        // Schema v1 only contained Windows NSIS releases. Keeping this legacy
        // fallback Windows-only prevents a Linux client from installing .exe.
        return cfg!(target_os = "windows");
    }
    candidate == update_platform()
}

fn validate_update_release(release: &UpdateRelease) -> Result<(), String> {
    if release.version.trim().is_empty() {
        return Err("update_version_missing".to_string());
    }
    if !release
        .url
        .starts_with("https://vps-910c1dbc.vps.ovh.net/downloads/")
    {
        return Err("update_url_untrusted".to_string());
    }
    let hash = release.sha256.trim();
    if hash.len() != 64 || !hash.chars().all(|character| character.is_ascii_hexdigit()) {
        return Err("update_sha256_invalid".to_string());
    }
    if release.content_id.trim().to_ascii_lowercase() != hash.to_ascii_lowercase() {
        return Err("update_content_id_mismatch".to_string());
    }
    if release.signing_key_id.trim() != UPDATE_SIGNING_KEY_ID {
        return Err("update_signing_key_untrusted".to_string());
    }
    verify_update_signature(release)?;
    Ok(())
}

fn update_signature_payload(release: &UpdateRelease) -> Vec<u8> {
    format!(
        "silicium-update-v1\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n",
        release.channel,
        release.platform,
        release.version,
        release.sha256.to_ascii_lowercase(),
        release.size_bytes,
        release.url,
        release.content_id.to_ascii_lowercase(),
    )
    .into_bytes()
}

fn legacy_update_signature_payload(release: &UpdateRelease) -> Vec<u8> {
    format!(
        "silicium-update-v1\n{}\n{}\n{}\n{}\n{}\n{}\n",
        release.channel,
        release.version,
        release.sha256.to_ascii_lowercase(),
        release.size_bytes,
        release.url,
        release.content_id.to_ascii_lowercase(),
    )
    .into_bytes()
}

fn verify_update_signature(release: &UpdateRelease) -> Result<(), String> {
    let public_key = BASE64_STANDARD
        .decode(UPDATE_SIGNING_PUBLIC_KEY_B64)
        .map_err(|_| "update_public_key_invalid".to_string())?;
    let public_key: [u8; 32] = public_key
        .try_into()
        .map_err(|_| "update_public_key_invalid".to_string())?;
    let verifying_key = VerifyingKey::from_bytes(&public_key)
        .map_err(|_| "update_public_key_invalid".to_string())?;
    let signature = BASE64_STANDARD
        .decode(release.signature.trim())
        .map_err(|_| "update_signature_invalid".to_string())?;
    let signature =
        Signature::from_slice(&signature).map_err(|_| "update_signature_invalid".to_string())?;
    if verifying_key
        .verify(&update_signature_payload(release), &signature)
        .is_ok()
    {
        return Ok(());
    }
    // Releases published before platform-specific artifacts were added did
    // not include `platform` in the signed payload. Accept that legacy form
    // only when the field is absent; a non-empty platform must be signed.
    if release.platform.trim().is_empty()
        && verifying_key
            .verify(&legacy_update_signature_payload(release), &signature)
            .is_ok()
    {
        return Ok(());
    }
    Err("update_signature_untrusted".to_string())
}

fn download_update(release: &UpdateRelease) -> Result<PathBuf, String> {
    let updates_dir = app_state_dir().join("updates");
    fs::create_dir_all(&updates_dir).map_err(|error| error.to_string())?;
    let safe_version = release
        .version
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '.' | '-') {
                character
            } else {
                '_'
            }
        })
        .collect::<String>();
    let extension = if cfg!(target_os = "windows") {
        "exe"
    } else {
        "AppImage"
    };
    let installer = updates_dir.join(format!("silicium-node-{safe_version}.{extension}"));
    if installer.is_file() {
        let metadata = fs::metadata(&installer).map_err(|error| error.to_string())?;
        let size_matches = release.size_bytes == 0 || metadata.len() == release.size_bytes;
        if size_matches && sha256_file(&installer)? == release.sha256.trim().to_ascii_lowercase() {
            cache_update_for_peers(&installer, &release.content_id);
            return Ok(installer);
        }
    }
    let primary_download = curl_download(&release.url, &installer, 300);
    if primary_download.is_err() {
        let fallback_url = format!(
            "http://127.0.0.1:46101/updates/content/{}",
            release.content_id.trim().to_ascii_lowercase()
        );
        curl_download(&fallback_url, &installer, 600).map_err(|fallback_error| {
            format!(
                "update_download_unavailable:primary={};gossip={fallback_error}",
                primary_download
                    .err()
                    .unwrap_or_else(|| "unknown".to_string())
            )
        })?;
    }
    let metadata = fs::metadata(&installer).map_err(|error| error.to_string())?;
    if release.size_bytes > 0 && metadata.len() != release.size_bytes {
        let _ = fs::remove_file(&installer);
        return Err(format!(
            "update_size_mismatch:{}:{}",
            metadata.len(),
            release.size_bytes
        ));
    }
    let actual_hash = sha256_file(&installer)?;
    if actual_hash != release.sha256.trim().to_ascii_lowercase() {
        let _ = fs::remove_file(&installer);
        return Err("update_sha256_mismatch".to_string());
    }
    cache_update_for_peers(&installer, &release.content_id);
    Ok(installer)
}

fn cache_update_for_peers(installer: &Path, content_id: &str) {
    let url = format!(
        "http://127.0.0.1:46101/updates/cache/{}",
        content_id.trim().to_ascii_lowercase()
    );
    let source = format!("@{}", installer.display());
    let _ = Command::new(curl_command())
        .arg("--silent")
        .arg("--show-error")
        .arg("--fail")
        .arg("--max-time")
        .arg("300")
        .arg("--request")
        .arg("POST")
        .arg("--data-binary")
        .arg(source)
        .arg(url)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

fn schedule_update_install(installer: &Path, release: &UpdateRelease) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        return schedule_linux_appimage_install(installer, release);
    }
    #[cfg(not(target_os = "linux"))]
    {
        schedule_update_install_non_linux(installer, release)
    }
}

#[cfg(target_os = "linux")]
fn schedule_linux_appimage_install(
    installer: &Path,
    release: &UpdateRelease,
) -> Result<(), String> {
    // Only an AppImage can be replaced by the unprivileged node process. RPM
    // and DEB installations remain package-manager managed and must not be
    // overwritten behind the user's back.
    let appimage = env::var_os("APPIMAGE")
        .map(PathBuf::from)
        .filter(|path| path.is_file())
        .and_then(|path| path.canonicalize().ok())
        .ok_or_else(|| "automatic_update_requires_appimage".to_string())?;
    let script_path = app_state_dir().join("apply-update.sh");
    let log_path = app_state_dir().join("update-install.log");
    let script = r#"#!/bin/sh
set -u

PARENT_PID="$1"
NODE_PID="$2"
INSTALLER="$3"
APPIMAGE="$4"
REPO_ROOT="$5"
LOG_PATH="$6"
INSTALL_LOCK_PATH="$7"
FAILURE_PATH="$8"
CONTENT_ID="$9"
VERSION="${SILICIUM_UPDATE_VERSION:-unknown}"
BUILD="${SILICIUM_UPDATE_BUILD:-unknown}"

log_line() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG_PATH"
}

write_failure() {
  printf '{"contentId":"%s","version":"%s","build":"%s","error":"%s","failedAtUtc":"%s"}\n' \
    "$CONTENT_ID" "$VERSION" "$BUILD" "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$FAILURE_PATH"
}

restart_supervisor() {
  if [ -n "$REPO_ROOT" ] && [ -f "$APPIMAGE" ]; then
    nohup "$APPIMAGE" --supervisor --repo-root "$REPO_ROOT" >> "$LOG_PATH" 2>&1 </dev/null &
  fi
}

fail_update() {
  log_line "update_failed $1"
  write_failure "$1"
  rm -f "$INSTALL_LOCK_PATH"
  restart_supervisor
  exit 1
}

# The current supervisor is executing the AppImage from its temporary mount.
# Wait for it to exit before replacing the stable AppImage file and starting
# a fresh supervisor from that stable path.
while kill -0 "$PARENT_PID" 2>/dev/null; do
  sleep 0.25
done

case "$NODE_PID" in
  ''|0|*[!0-9]*) ;;
  *)
    kill -TERM "$NODE_PID" 2>/dev/null || true
    attempts=0
    while kill -0 "$NODE_PID" 2>/dev/null && [ "$attempts" -lt 40 ]; do
      sleep 0.25
      attempts=$((attempts + 1))
    done
    kill -KILL "$NODE_PID" 2>/dev/null || true
    ;;
esac

if [ -n "$REPO_ROOT" ]; then
  rm -f "$REPO_ROOT/.silicium/node-app/silicium-node.pid"
fi
if [ ! -f "$INSTALLER" ]; then
  fail_update "linux_update_artifact_missing"
fi
if [ ! -w "$(dirname "$APPIMAGE")" ]; then
  fail_update "linux_appimage_not_writable"
fi

temporary_appimage="$APPIMAGE.new.$$"
if ! cp "$INSTALLER" "$temporary_appimage"; then
  fail_update "linux_appimage_copy_failed"
fi
if ! chmod 0755 "$temporary_appimage"; then
  rm -f "$temporary_appimage"
  fail_update "linux_appimage_permission_failed"
fi
if ! mv -f "$temporary_appimage" "$APPIMAGE"; then
  rm -f "$temporary_appimage"
  fail_update "linux_appimage_replace_failed"
fi

rm -f "$FAILURE_PATH" "$INSTALL_LOCK_PATH"
log_line "update_installed $APPIMAGE"
nohup "$APPIMAGE" --supervisor --repo-root "$REPO_ROOT" >> "$LOG_PATH" 2>&1 </dev/null &
exit 0
"#;
    fs::write(&script_path, script).map_err(|error| error.to_string())?;
    let runtime_root = discover_managed_runtime_root();
    let node_pid = runtime_root
        .as_ref()
        .and_then(|root| read_pid(root).ok().flatten())
        .unwrap_or(0);
    let repo_root = runtime_root
        .as_ref()
        .map(|root| root.display().to_string())
        .unwrap_or_default();
    let mut command = Command::new("sh");
    command
        .arg(&script_path)
        .arg(std::process::id().to_string())
        .arg(node_pid.to_string())
        .arg(installer)
        .arg(&appimage)
        .arg(&repo_root)
        .arg(&log_path)
        .arg(update_install_lock_path())
        .arg(update_install_failure_path())
        .arg(&release.content_id)
        .env("SILICIUM_UPDATE_VERSION", &release.version)
        .env("SILICIUM_UPDATE_BUILD", &release.build)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command.spawn().map_err(|error| error.to_string())?;
    release_update_lock();
    std::process::exit(0);
}

#[cfg(not(target_os = "linux"))]
fn schedule_update_install_non_linux(
    installer: &Path,
    release: &UpdateRelease,
) -> Result<(), String> {
    if !cfg!(target_os = "windows") {
        return Err(format!(
            "automatic_update_installer_not_available:{}",
            update_platform()
        ));
    }
    let script_path = app_state_dir().join("apply-update.ps1");
    let log_path = app_state_dir().join("update-install.log");
    let script = r#"param(
  [int]$ParentPid,
  [int]$NodePid,
  [string]$Installer,
  [string]$Executable,
  [string]$RepoRoot,
  [string]$LogPath,
  [string]$InstallLockPath,
  [string]$FailurePath,
  [string]$ContentId,
  [string]$Version,
  [string]$Build
)
$ErrorActionPreference = 'Stop'
try {
  while (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 250 }
  if ($NodePid -gt 0) { & taskkill.exe /PID $NodePid /T /F | Out-Null }
  if ($RepoRoot) {
    Get-CimInstance Win32_Process | Where-Object {
      $_.ProcessId -ne $PID -and
      $_.CommandLine -and
      $_.CommandLine.IndexOf('silicium node start', [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
      $_.CommandLine.IndexOf($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    } | ForEach-Object {
      & taskkill.exe /PID $_.ProcessId /T /F | Out-Null
      Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) stale_node_runtime_stopped pid=$($_.ProcessId)"
    }
    Remove-Item -LiteralPath (Join-Path $RepoRoot '.silicium\node-app\silicium-node.pid') -Force -ErrorAction SilentlyContinue
  }
  Get-Process -Name 'silicium-node' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
  $process = $null
  for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
      $process = Start-Process -FilePath $Installer -ArgumentList '/S' -Wait -PassThru
      break
    } catch {
      Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) installer_launch_retry attempt=$attempt error=$($_.Exception.Message)"
      if ($attempt -eq 30) { throw }
      Start-Sleep -Seconds 2
    }
  }
  if ($null -eq $process) { throw 'installer_not_started' }
  if ($process.ExitCode -ne 0) { throw "installer_exit_$($process.ExitCode)" }
  Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) update_installed $Installer"
  if ($RepoRoot -and (Test-Path -LiteralPath (Join-Path $RepoRoot '.silicium\node-app\service-config.env'))) {
    Start-Process -FilePath $Executable -ArgumentList '--background' -WindowStyle Hidden
    Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) notification_shell_restarted $RepoRoot"
  } else {
    Start-Process -FilePath $Executable
  }
} catch {
  $errorMessage = $_.Exception.Message
  Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) update_failed $errorMessage"
  if ($FailurePath) {
    $failure = @{
      contentId = $ContentId
      version = $Version
      build = $Build
      error = $errorMessage
      failedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Compress
    Set-Content -LiteralPath $FailurePath -Value $failure -Encoding UTF8
  }
  if ($RepoRoot -and (Test-Path -LiteralPath (Join-Path $RepoRoot '.silicium\node-app\service-config.env'))) {
    $quotedRepoRoot = '"' + $RepoRoot + '"'
    Start-Process -FilePath $Executable -ArgumentList '--supervisor', '--repo-root', $quotedRepoRoot -WindowStyle Hidden
    Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) supervisor_recovered_after_update_failure $RepoRoot"
  }
  Start-Process -FilePath $Executable
  exit 1
} finally {
  if ($InstallLockPath) {
    Remove-Item -LiteralPath $InstallLockPath -Force -ErrorAction SilentlyContinue
  }
}
"#;
    fs::write(&script_path, script).map_err(|error| error.to_string())?;
    let executable = env::current_exe().map_err(|error| error.to_string())?;
    let runtime_root = discover_managed_runtime_root();
    let node_pid = runtime_root
        .as_ref()
        .and_then(|root| read_pid(root).ok().flatten())
        .unwrap_or(0);
    let repo_root = runtime_root
        .as_ref()
        .map(|root| root.display().to_string())
        .unwrap_or_default();
    let mut command = Command::new("powershell.exe");
    command
        .arg("-NoProfile")
        .arg("-NonInteractive")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-File")
        .arg(&script_path)
        .arg("-ParentPid")
        .arg(std::process::id().to_string())
        .arg("-NodePid")
        .arg(node_pid.to_string())
        .arg("-Installer")
        .arg(installer)
        .arg("-Executable")
        .arg(executable)
        .arg("-RepoRoot")
        .arg(repo_root)
        .arg("-LogPath")
        .arg(log_path)
        .arg("-InstallLockPath")
        .arg(update_install_lock_path())
        .arg("-FailurePath")
        .arg(update_install_failure_path())
        .arg("-ContentId")
        .arg(&release.content_id)
        .arg("-Version")
        .arg(&release.version)
        .arg("-Build")
        .arg(&release.build)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    configure_detached_process(&mut command);
    command.spawn().map_err(|error| error.to_string())?;
    release_update_lock();
    std::process::exit(0);
}

fn curl_get(url: &str, timeout_seconds: u64) -> Result<String, String> {
    let mut command = Command::new(curl_command());
    command
        .arg("-4")
        .arg("--fail")
        .arg("--silent")
        .arg("--show-error")
        .arg("--location")
        .arg("--max-time")
        .arg(timeout_seconds.to_string())
        .arg(url)
        .stdin(Stdio::null());
    configure_detached_process(&mut command);
    let output = command
        .output()
        .map_err(|error| format!("curl_start_failed:{error}"))?;
    if !output.status.success() {
        return Err(format!(
            "curl_failed:{}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn curl_download(url: &str, target: &Path, timeout_seconds: u64) -> Result<(), String> {
    let mut command = Command::new(curl_command());
    command
        .arg("-4")
        .arg("--fail")
        .arg("--silent")
        .arg("--show-error")
        .arg("--location")
        .arg("--max-time")
        .arg(timeout_seconds.to_string())
        .arg("--output")
        .arg(target)
        .arg(url)
        .stdin(Stdio::null());
    configure_detached_process(&mut command);
    let output = command
        .output()
        .map_err(|error| format!("curl_start_failed:{error}"))?;
    if !output.status.success() {
        return Err(format!(
            "curl_failed:{}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(())
}

fn curl_command() -> &'static str {
    if cfg!(target_os = "windows") {
        "curl.exe"
    } else {
        "curl"
    }
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(|error| error.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn current_utc() -> String {
    DateTime::<Utc>::from(SystemTime::now()).to_rfc3339_opts(SecondsFormat::Secs, true)
}

fn run_background_update_loop() {
    loop {
        let status = check_for_update_once(true);
        thread::sleep(Duration::from_secs(status.check_interval_seconds.max(15)));
    }
}

#[cfg(test)]
fn version_is_newer(candidate: &str, current: &str) -> bool {
    compare_versions(candidate, current) == Ordering::Greater
}

fn release_requires_update(
    candidate_version: &str,
    candidate_build: &str,
    current_version: &str,
    current_build: &str,
) -> bool {
    match compare_versions(candidate_version, current_version) {
        Ordering::Greater => true,
        Ordering::Less => false,
        Ordering::Equal => {
            let candidate_build = candidate_build.trim();
            !candidate_build.is_empty() && candidate_build != current_build.trim()
        }
    }
}

fn compare_versions(left: &str, right: &str) -> Ordering {
    let parse = |value: &str| {
        let clean = value.trim().trim_start_matches('v');
        let mut sections = clean.splitn(2, '-');
        let core = sections
            .next()
            .unwrap_or("")
            .split('.')
            .map(|part| part.parse::<u64>().unwrap_or(0))
            .collect::<Vec<_>>();
        let pre = sections.next().unwrap_or("").to_string();
        (core, pre)
    };
    let (left_core, left_pre) = parse(left);
    let (right_core, right_pre) = parse(right);
    for index in 0..left_core.len().max(right_core.len()).max(3) {
        let ordering = left_core
            .get(index)
            .copied()
            .unwrap_or(0)
            .cmp(&right_core.get(index).copied().unwrap_or(0));
        if ordering != Ordering::Equal {
            return ordering;
        }
    }
    match (left_pre.is_empty(), right_pre.is_empty()) {
        (true, false) => Ordering::Greater,
        (false, true) => Ordering::Less,
        (true, true) => Ordering::Equal,
        (false, false) => {
            let left_parts = left_pre.split('.').collect::<Vec<_>>();
            let right_parts = right_pre.split('.').collect::<Vec<_>>();
            for index in 0..left_parts.len().max(right_parts.len()) {
                let left_part = left_parts.get(index).copied().unwrap_or("");
                let right_part = right_parts.get(index).copied().unwrap_or("");
                let ordering = match (left_part.parse::<u64>(), right_part.parse::<u64>()) {
                    (Ok(left_number), Ok(right_number)) => left_number.cmp(&right_number),
                    (Ok(_), Err(_)) => Ordering::Less,
                    (Err(_), Ok(_)) => Ordering::Greater,
                    (Err(_), Err(_)) => left_part.cmp(right_part),
                };
                if ordering != Ordering::Equal {
                    return ordering;
                }
            }
            Ordering::Equal
        }
    }
}

fn resolve_optional_repo_root(_repo_root: Option<&str>) -> Option<PathBuf> {
    if let Some(root) = discover_managed_runtime_root() {
        return Some(root);
    }
    ensure_packaged_runtime_preferred()
}

fn resolve_repo_root(_repo_root: &str) -> Result<PathBuf, String> {
    if let Some(root) = discover_managed_runtime_root() {
        return refresh_managed_runtime_if_needed(root);
    }
    if find_packaged_runtime_root().is_some() {
        return ensure_managed_runtime();
    }
    Err("managed_runtime_not_found".to_string())
}

fn resolve_repo_root_readonly(_repo_root: &str) -> Result<PathBuf, String> {
    if let Some(root) = discover_managed_runtime_root() {
        validate_repo_root(&root)?;
        return Ok(root);
    }
    if find_packaged_runtime_root().is_some() {
        return ensure_managed_runtime();
    }
    Err("managed_runtime_not_found".to_string())
}

fn ensure_packaged_runtime_preferred() -> Option<PathBuf> {
    if find_packaged_runtime_root().is_some() {
        ensure_managed_runtime().ok()
    } else {
        None
    }
}

fn validate_repo_root(repo_root: &Path) -> Result<(), String> {
    if !repo_root.exists() {
        return Err("repo_root_not_found".to_string());
    }
    if !repo_root.join("Network").is_dir() {
        return Err("network_directory_not_found".to_string());
    }
    if !repo_root.join("Network").join("silicium").is_file() {
        return Err("network_runtime_not_found".to_string());
    }
    Ok(())
}

fn managed_runtime_root() -> PathBuf {
    app_state_dir().join("runtime")
}

fn discover_managed_runtime_root() -> Option<PathBuf> {
    let root = managed_runtime_root();
    if validate_repo_root(&root).is_ok() {
        Some(root)
    } else {
        None
    }
}

fn ensure_managed_runtime() -> Result<PathBuf, String> {
    let root = managed_runtime_root();
    let source = find_packaged_runtime_root().ok_or_else(|| {
        format!(
            "managed_runtime_missing: no bundled runtime found. Expected an installed runtime with Network/ under {}",
            root.display()
        )
    })?;
    if same_path(&source, &root) {
        remove_legacy_runtime_assets(&root)?;
        validate_repo_root(&root)?;
        return Ok(root);
    }

    copy_dir_all(&source, &root)?;
    remove_legacy_runtime_assets(&root)?;
    validate_repo_root(&root)?;
    Ok(root)
}

fn remove_legacy_runtime_assets(root: &Path) -> Result<(), String> {
    // Releases before dev.14 bundled the OpenSSL CLI and added it to PATH.
    // NSIS upgrades and the managed-runtime copy are additive, so files that
    // disappear from a newer bundle otherwise survive forever. Cryptography
    // uses its own Python extension and does not need this executable.
    let legacy_openssl = root.join("tools").join("openssl");
    if legacy_openssl.exists() {
        fs::remove_dir_all(&legacy_openssl).map_err(|error| {
            format!(
                "legacy_runtime_cleanup_failed:{}:{error}",
                legacy_openssl.display()
            )
        })?;
    }
    // The integrated Python daemon only needs networked_runtime.py. Older
    // bundles copied the complete Rust workspaces, including Cargo targets,
    // into the user profile. Besides wasting disk, that allowed the CLI to
    // compile an experimental node during activation.
    let legacy_networked_crates = root.join("Network").join("networked");
    for crate_name in [
        "compute_daemon",
        "p2p_node",
        "reputation_bridge",
        "silicium_node_core",
    ] {
        let path = legacy_networked_crates.join(crate_name);
        if path.exists() {
            fs::remove_dir_all(&path).map_err(|error| {
                format!("legacy_runtime_cleanup_failed:{}:{error}", path.display())
            })?;
        }
    }
    let legacy_raytracer_target = root
        .join("Network")
        .join("workloads")
        .join("raytracer")
        .join("native")
        .join("target");
    if legacy_raytracer_target.exists() {
        fs::remove_dir_all(&legacy_raytracer_target).map_err(|error| {
            format!(
                "legacy_runtime_cleanup_failed:{}:{error}",
                legacy_raytracer_target.display()
            )
        })?;
    }
    Ok(())
}

fn refresh_managed_runtime_if_needed(root: PathBuf) -> Result<PathBuf, String> {
    if !same_path(&root, &managed_runtime_root()) {
        return Ok(root);
    }
    ensure_managed_runtime()
}

fn is_managed_runtime_root(root: &Path) -> bool {
    same_path(root, &managed_runtime_root())
}

fn find_packaged_runtime_root() -> Option<PathBuf> {
    let exe = env::current_exe().ok();
    let app_dir = env::var_os("APPDIR")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from);
    let mut candidates = exe
        .as_deref()
        .map(|path| packaged_runtime_candidates(path, app_dir.as_deref()))
        .unwrap_or_default();
    candidates.push(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("resources")
            .join("runtime"),
    );

    candidates
        .into_iter()
        .find(|path| validate_repo_root(path).is_ok())
}

fn packaged_runtime_candidates(exe: &Path, app_dir: Option<&Path>) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    let executable_name = exe.file_stem().filter(|name| !name.is_empty());

    if cfg!(target_os = "linux") {
        // Tauri's Linux resource directory is /usr/lib/<binary>/ for both
        // AppImage and .deb bundles. AppImage exposes the mounted root as
        // APPDIR; keep both forms because current_exe() can be resolved from
        // a wrapper or from an extracted AppImage.
        if let Some(app_dir) = app_dir {
            candidates.extend(linux_resource_runtime_candidates(
                &app_dir.join("usr").join("lib"),
                executable_name,
            ));
        }

        // linuxdeploy's AppRun.wrapped can be reported as current_exe()
        // without exporting APPDIR. Walk its ancestors so a supervisor
        // started by XDG autostart can still find the mounted AppImage
        // resources instead of falling back to a stale managed runtime.
        let mut ancestor = exe.parent();
        while let Some(path) = ancestor {
            candidates.push(
                path.join("usr")
                    .join("lib")
                    .join("Silicium Node")
                    .join("resources")
                    .join("runtime"),
            );
            ancestor = path.parent();
        }
    }

    if let Some(parent) = exe.parent() {
        candidates.push(parent.join("runtime"));
        candidates.push(parent.join("resources").join("runtime"));

        if cfg!(target_os = "linux") {
            // Installed .deb/.rpm: /usr/bin/<binary> -> /usr/lib/<product>
            // name/resources/runtime. Tauri uses productName for the resource
            // directory, so it may contain spaces and differ from the binary
            // name (for example, "Silicium Node" vs "silicium-node").
            candidates.extend(linux_resource_runtime_candidates(
                &parent.join("..").join("lib"),
                executable_name,
            ));
        }

        // Keep the Windows and macOS layouts used by the existing desktop
        // build, as well as Tauri's macOS-style fallback.
        candidates.push(parent.join("..").join("Resources").join("runtime"));
    }

    candidates
}

fn linux_resource_runtime_candidates(
    lib_dir: &Path,
    executable_name: Option<&OsStr>,
) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(name) = executable_name {
        candidates.push(
            lib_dir
                .join(Path::new(name))
                .join("resources")
                .join("runtime"),
        );
    }
    let Ok(entries) = fs::read_dir(lib_dir) else {
        return candidates;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            candidates.push(path.join("resources").join("runtime"));
        }
    }
    candidates
}

fn same_path(left: &Path, right: &Path) -> bool {
    match (left.canonicalize(), right.canonicalize()) {
        (Ok(left), Ok(right)) => left == right,
        _ => left == right,
    }
}

fn copy_dir_all(source: &Path, target: &Path) -> Result<(), String> {
    fs::create_dir_all(target).map_err(|error| error.to_string())?;
    for entry in fs::read_dir(source).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if source_path.is_dir() && source_path.ends_with(Path::new("tools").join("openssl")) {
            // Old NSIS upgrades can retain this directory in the packaged
            // resources. Never copy it back into the managed runtime, even
            // when two runtime refreshes overlap.
            continue;
        }
        if source_path.is_dir() {
            copy_dir_all(&source_path, &target_path)?;
        } else {
            if let Some(parent) = target_path.parent() {
                fs::create_dir_all(parent).map_err(|error| error.to_string())?;
            }
            fs::copy(&source_path, &target_path).map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

fn spawn_node(repo_root: &Path, config: &NodeConfig) -> Result<Child, String> {
    let advertise_host = if config.advertise_host.trim().is_empty() {
        detect_local_ip().unwrap_or_else(|| "127.0.0.1".to_string())
    } else {
        config.advertise_host.trim().to_string()
    };

    if cfg!(target_os = "windows") {
        let network_root = repo_root.join("Network");
        let silicium_cli = network_root.join("silicium");
        if !silicium_cli.exists() {
            return Err(format!(
                "silicium_cli_not_found: {}",
                silicium_cli.display()
            ));
        }
        let node_id = effective_node_id(&config.node_id);
        let mut command = Command::new(python_launcher(repo_root));
        command
            .arg(&silicium_cli)
            .arg("node")
            .arg("start")
            .arg("--roles")
            .arg("compute,verify")
            .arg("--node-id")
            .arg(node_id)
            .arg("--app-version")
            .arg(release_version())
            .arg("--release-channel")
            .arg(release_channel())
            .arg("--release-build")
            .arg(release_build())
            .arg("--export-dir")
            .arg(".silicium\\networked\\silicium-desktop-node\\export")
            .arg("--state-dir")
            .arg(".silicium\\networked\\silicium-desktop-node\\state")
            .arg("--peer-http-bind")
            .arg("0.0.0.0")
            .arg("--peer-http-port")
            .arg("46101")
            .arg("--gossip-bind")
            .arg("0.0.0.0")
            .arg("--gossip-port")
            .arg("46101")
            .arg("--peer-advertise-host")
            .arg(&advertise_host)
            .arg("--peer-advertise-port")
            .arg("46101")
            .arg("--gossip-advertise-host")
            .arg(&advertise_host)
            .arg("--gossip-advertise-port")
            .arg("46101")
            .arg("--seed-peers")
            .arg(&config.orchestrator_url)
            .arg("--mesh-key")
            .arg("demo-mesh")
            .arg("--reputation-score")
            .arg(config.reputation_score.to_string())
            .arg("--peer-sync-interval-s")
            .arg("5")
            .arg("--peer-sync-fanout")
            .arg("8")
            .arg("--peer-stale-after-s")
            .arg("15")
            .arg("--peer-http-max-workers")
            .arg(env::var("SILICIUM_PEER_HTTP_MAX_WORKERS").unwrap_or_else(|_| "16".to_string()))
            .arg("--idle-ms")
            .arg("250")
            .arg("--pull-tasks-enable")
            .arg("--pull-tasks-interval-s")
            .arg("0.25")
            .arg("--pull-tasks-batch-size")
            .arg(env::var("SILICIUM_PULL_TASKS_BATCH_SIZE").unwrap_or_else(|_| "4".to_string()))
            .arg("--gossip-enable")
            .arg("--nat-punch-enable")
            .arg("--p2p-direct-transport-backend")
            .arg("auto")
            .current_dir(&network_root);
        command.env("SILICIUM_IDENTITY_MODE", "hmac");
        command.env("SILICIUM_FORCE_HMAC_IDENTITY", "1");
        apply_raytracer_env(&mut command, repo_root);
        apply_runtime_path(&mut command, repo_root);
        spawn_detached(command, repo_root)
    } else {
        let script = repo_root.join("deploy").join("linux").join("start-node.sh");
        if !script.exists() {
            return Err(format!("script_not_found: {}", script.display()));
        }
        let mut command = Command::new("bash");
        command
            .arg(script)
            .arg(effective_node_id(&config.node_id))
            .arg("compute,verify")
            .arg("46101")
            .arg(&config.orchestrator_url)
            .arg(&advertise_host)
            .arg("demo-mesh")
            .arg(config.reputation_score.to_string())
            .arg("--app-version")
            .arg(release_version())
            .arg("--release-channel")
            .arg(release_channel())
            .arg("--release-build")
            .arg(release_build())
            .arg("--gossip-enable")
            .arg("--nat-punch-enable")
            .arg("--p2p-direct-transport-backend")
            .arg("auto")
            .current_dir(repo_root);
        apply_raytracer_env(&mut command, repo_root);
        apply_runtime_path(&mut command, repo_root);
        spawn_detached(command, repo_root)
    }
}

fn wait_for_supervised_node_start(
    supervisor: &mut Child,
    repo_root: &Path,
    port: u16,
) -> Result<(), String> {
    let deadline = Instant::now() + NODE_READY_TIMEOUT;
    let supervisor_pid = supervisor.id();
    loop {
        if local_network_node_ready(port) {
            return Ok(());
        }
        if let Some(status) = supervisor.try_wait().map_err(|error| error.to_string())? {
            let replacement_running = read_supervisor_pid(repo_root)
                .ok()
                .flatten()
                .filter(|pid| *pid != supervisor_pid)
                .map(process_is_running)
                .unwrap_or(false);
            if !replacement_running {
                remove_supervisor_pid(repo_root);
                let logs = read_node_log_tail(repo_root);
                return Err(format!(
                    "supervisor_exited_before_ready: {status}\n{}",
                    logs.unwrap_or_else(|| "No supervisor logs available yet.".to_string())
                ));
            }
        }
        if Instant::now() >= deadline {
            let logs = read_node_log_tail(repo_root);
            return Err(format!(
                "node_not_ready_after_supervisor_start\n{}",
                logs.unwrap_or_else(|| "No node logs available yet.".to_string())
            ));
        }
        thread::sleep(Duration::from_millis(300));
    }
}

fn wait_for_existing_node_start(repo_root: &Path, port: u16) -> bool {
    let deadline = Instant::now() + NODE_READY_TIMEOUT;
    loop {
        if local_network_node_ready(port) {
            return true;
        }
        cleanup_dead_pids(repo_root);
        let supervisor_running = read_supervisor_pid(repo_root)
            .ok()
            .flatten()
            .map(process_is_running)
            .unwrap_or(false);
        let node_running = read_pid(repo_root)
            .ok()
            .flatten()
            .map(process_is_running)
            .unwrap_or(false);
        if !supervisor_running && !node_running {
            return false;
        }
        if Instant::now() >= deadline {
            return false;
        }
        thread::sleep(Duration::from_millis(300));
    }
}

fn local_network_node_ready(port: u16) -> bool {
    let Ok(address) = format!("127.0.0.1:{port}").parse() else {
        return false;
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(700)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(700)));
    if stream
        .write_all(b"GET /healthz HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut response = String::new();
    let _ = stream.read_to_string(&mut response);
    (response.starts_with("HTTP/1.0 200") || response.starts_with("HTTP/1.1 200"))
        && response.contains("\"service\":\"network_node\"")
        && response.contains("\"ok\":true")
}

fn wait_for_local_port_release(port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    loop {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return true;
        }
        if Instant::now() >= deadline {
            return false;
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn reset_node_session_logs(repo_root: &Path) -> Result<(), String> {
    for name in [
        "silicium-supervisor.out.log",
        "silicium-supervisor.err.log",
        "silicium-node.out.log",
        "silicium-node.err.log",
    ] {
        let path = node_app_log_path(repo_root, name);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(path)
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn spawn_supervisor(repo_root: &Path) -> Result<Child, String> {
    reset_node_session_logs(repo_root)?;
    let exe = env::current_exe().map_err(|error| error.to_string())?;
    let mut command = Command::new(exe);
    command
        .arg("--supervisor")
        .arg("--repo-root")
        .arg(repo_root.display().to_string())
        .current_dir(repo_root);
    spawn_detached_with_log(
        command,
        repo_root,
        "silicium-supervisor.out.log",
        "silicium-supervisor.err.log",
    )
}

fn install_autostart_task(repo_root: &Path) -> Result<(), String> {
    if cfg!(target_os = "linux") {
        return install_linux_autostart(repo_root);
    }
    if !cfg!(target_os = "windows") {
        return Ok(());
    }
    let exe = env::current_exe().map_err(|error| error.to_string())?;
    let task_command = windows_autostart_command(&exe);
    let mut command = Command::new("schtasks");
    command
        .arg("/Create")
        .arg("/TN")
        .arg(SUPERVISOR_TASK_NAME)
        .arg("/SC")
        .arg("ONLOGON")
        .arg("/TR")
        .arg(&task_command)
        .arg("/F")
        .stdin(Stdio::null());
    configure_detached_process(&mut command);
    let output = command.output().map_err(|error| error.to_string())?;
    if output.status.success() {
        return Ok(());
    }
    match install_autostart_run_key(&task_command) {
        Ok(()) => Ok(()),
        Err(registry_error) => {
            let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            Err(format!(
                "{}{}{}; registry fallback failed: {}",
                output.status,
                if stdout.is_empty() && stderr.is_empty() {
                    ""
                } else {
                    ": "
                },
                if stderr.is_empty() { stdout } else { stderr },
                registry_error
            ))
        }
    }
}

fn install_linux_autostart(repo_root: &Path) -> Result<(), String> {
    let home = env::var("HOME").map_err(|_| "home_directory_not_found".to_string())?;
    let autostart_dir = PathBuf::from(home).join(".config").join("autostart");
    fs::create_dir_all(&autostart_dir).map_err(|error| error.to_string())?;
    let executable = linux_autostart_executable()?;
    let quote = |value: &Path| {
        value
            .display()
            .to_string()
            .replace('\\', "\\\\")
            .replace('"', "\\\"")
    };
    let entry = format!(
        "[Desktop Entry]\nType=Application\nName=Silicium Node\nComment=Silicium P2P compute worker\nExec=\"{}\" --supervisor --repo-root \"{}\"\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
        quote(&executable),
        quote(repo_root),
    );
    fs::write(autostart_dir.join("network.silicium.node.desktop"), entry)
        .map_err(|error| error.to_string())
}

fn linux_autostart_executable() -> Result<PathBuf, String> {
    if cfg!(target_os = "linux") {
        // An AppImage runs its binary from a temporary mount. Persisting that
        // path in XDG autostart would leave a dead entry after the process
        // exits. APPIMAGE points to the user's stable downloaded file.
        if let Some(appimage) = env::var_os("APPIMAGE") {
            let path = PathBuf::from(appimage);
            if path.is_file() {
                return Ok(path);
            }
        }
    }
    env::current_exe().map_err(|error| error.to_string())
}

fn install_autostart_run_key(task_command: &str) -> Result<(), String> {
    if !cfg!(target_os = "windows") {
        return Ok(());
    }
    let mut command = Command::new("reg");
    command
        .arg("add")
        .arg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run")
        .arg("/V")
        .arg(SUPERVISOR_RUN_KEY_NAME)
        .arg("/T")
        .arg("REG_SZ")
        .arg("/D")
        .arg(task_command)
        .arg("/F")
        .stdin(Stdio::null());
    configure_detached_process(&mut command);
    let output = command.output().map_err(|error| error.to_string())?;
    if output.status.success() {
        Ok(())
    } else {
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        Err(format!(
            "{}{}{}",
            output.status,
            if stdout.is_empty() { "" } else { ": " },
            if stderr.is_empty() { stdout } else { stderr }
        ))
    }
}

fn uninstall_autostart_task() {
    if cfg!(target_os = "linux") {
        if let Ok(home) = env::var("HOME") {
            let _ = fs::remove_file(
                PathBuf::from(home)
                    .join(".config")
                    .join("autostart")
                    .join("network.silicium.node.desktop"),
            );
        }
        return;
    }
    if !cfg!(target_os = "windows") {
        return;
    }
    let mut schtasks = Command::new("schtasks");
    schtasks
        .arg("/Delete")
        .arg("/TN")
        .arg(SUPERVISOR_TASK_NAME)
        .arg("/F")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    configure_detached_process(&mut schtasks);
    let _ = schtasks.status();
    let mut reg = Command::new("reg");
    reg.arg("delete")
        .arg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run")
        .arg("/V")
        .arg(SUPERVISOR_RUN_KEY_NAME)
        .arg("/F")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    configure_detached_process(&mut reg);
    let _ = reg.status();
}

pub fn run_supervisor_cli() -> i32 {
    let mut repo_root = String::new();
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--repo-root" {
            repo_root = args.next().unwrap_or_default();
        }
    }
    // The supervisor is also the Linux autostart entrypoint. It must refresh
    // the persistent runtime from the currently mounted AppImage before it
    // starts the network child; using the readonly resolver here left an old
    // start-node.sh in ~/.config after an AppImage update.
    let repo_root = match resolve_repo_root(&repo_root) {
        Ok(root) => root,
        Err(error) => {
            let _ = append_app_log(&format!("supervisor_start_failed: {error}\n"));
            return 2;
        }
    };
    if let Err(error) = remove_legacy_runtime_assets(&repo_root) {
        let _ = append_supervisor_log(
            &repo_root,
            &format!("legacy_runtime_cleanup_failed: {error}\n"),
        );
    }
    if validate_repo_root(&repo_root).is_err() {
        return 2;
    }
    match claim_supervisor_pid(&repo_root) {
        Ok(true) => {}
        Ok(false) => return 0,
        Err(error) => {
            let _ =
                append_supervisor_log(&repo_root, &format!("supervisor_lease_failed: {error}\n"));
            return 2;
        }
    }
    // A supervisor launched directly by XDG autostart does not pass through
    // spawn_supervisor(), so the previous session's Python traceback would
    // otherwise remain in the diagnostic tail after a successful recovery.
    // Reset only after taking the lease: a second supervisor must never wipe
    // logs belonging to the active one.
    if let Err(error) = reset_node_session_logs(&repo_root) {
        let _ = append_supervisor_log(
            &repo_root,
            &format!("session_log_reset_failed: {error}\n"),
        );
    }
    // An older updater may have lost silicium-node.pid while leaving the
    // Python network runtime alive. Replace it on supervisor startup so the
    // advertised app version/build always matches this executable.
    kill_managed_node_processes(&repo_root);
    remove_pid(&repo_root);
    thread::spawn(run_background_update_loop);
    let config = read_service_config(&repo_root).unwrap_or_else(|_| NodeConfig {
        repo_root: repo_root.display().to_string(),
        orchestrator_url: DEFAULT_ORCHESTRATOR_URL.to_string(),
        advertise_host: detect_local_ip().unwrap_or_else(|| "127.0.0.1".to_string()),
        node_id: "silicium-desktop-node".to_string(),
        reputation_score: 100,
    });

    let mut restart_attempts = 0_u32;
    let mut node_started_at = Instant::now();
    loop {
        cleanup_dead_pids(&repo_root);
        let pid_running = read_pid(&repo_root)
            .ok()
            .flatten()
            .map(process_is_running)
            .unwrap_or(false);
        let mut node_running = pid_running;
        if node_running
            && node_started_at.elapsed() >= CLAIM_POLL_STALE_AFTER
            && !local_network_node_ready(46101)
            && !claim_poll_is_fresh(&repo_root, CLAIM_POLL_STALE_AFTER)
        {
            let _ = append_supervisor_log(
                &repo_root,
                "claim_poll_stale: restarting the managed network node",
            );
            if let Ok(Some(pid)) = read_pid(&repo_root) {
                let _ = kill_process_tree(pid);
            }
            // Older Linux bundles tracked the shell wrapper instead of the
            // Python child. Reap both the recorded tree and any orphaned
            // managed launcher before trying to bind the node port again.
            kill_known_silicium_processes(Some(&repo_root));
            remove_pid(&repo_root);
            node_running = false;
            let _ = wait_for_local_port_release(46101, Duration::from_secs(2));
        }
        if node_running {
            restart_attempts = 0;
        }
        if !node_running {
            remove_pid(&repo_root);
            kill_known_silicium_processes(Some(&repo_root));
            if wait_for_local_port_release(46101, Duration::from_secs(2)) {
                match spawn_node(&repo_root, &config) {
                    Ok(child) => {
                        restart_attempts = restart_attempts.saturating_add(1);
                        node_started_at = Instant::now();
                        let _ = write_pid(&repo_root, child.id());
                        let _ = append_supervisor_log(
                            &repo_root,
                            &format!("node_started pid={}\n", child.id()),
                        );
                    }
                    Err(error) => {
                        let _ = append_supervisor_log(
                            &repo_root,
                            &format!("spawn_node_failed: {error}\n"),
                        );
                    }
                }
            } else {
                restart_attempts = restart_attempts.saturating_add(1);
                let _ = append_supervisor_log(
                    &repo_root,
                    "node_port_occupied: waiting before retrying managed network node",
                );
            }
        }
        let delay = if restart_attempts > 3 { 20 } else { 5 };
        thread::sleep(Duration::from_secs(delay));
    }
}

fn claim_poll_health_path(repo_root: &Path) -> PathBuf {
    repo_root
        .join("Network")
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node")
        .join("export")
        .join("claim-poll.health.json")
}

fn claim_poll_is_fresh(repo_root: &Path, maximum_age: Duration) -> bool {
    let path = claim_poll_health_path(repo_root);
    if !path.exists() {
        // The caller already applies a bootstrap grace period. Beyond it, a
        // missing file means that the scheduler pull loop never became live.
        return false;
    }
    fs::metadata(path)
        .and_then(|metadata| metadata.modified())
        .ok()
        .and_then(|modified| SystemTime::now().duration_since(modified).ok())
        .map(|age| age <= maximum_age)
        .unwrap_or(false)
}

fn detect_local_ip() -> Option<String> {
    let socket = UdpSocket::bind("0.0.0.0:0").ok()?;
    socket.connect("8.8.8.8:80").ok()?;
    Some(socket.local_addr().ok()?.ip().to_string())
}

fn python_launcher(repo_root: &Path) -> String {
    if cfg!(target_os = "linux") {
        if let Ok(configured) = env::var("SILICIUM_PYTHON3") {
            if !configured.trim().is_empty() {
                return configured;
            }
        }
        for candidate in ["/usr/bin/python3", "/usr/local/bin/python3"] {
            if Path::new(candidate).exists() {
                return candidate.to_string();
            }
        }
        return "python3".to_string();
    }
    if !cfg!(target_os = "windows") {
        return "python3".to_string();
    }
    let mut candidates = Vec::new();
    candidates.push(repo_root.join("tools").join("python").join("python.exe"));
    candidates.push(repo_root.join("tools").join("python").join("python3.exe"));
    candidates.push(repo_root.join("python").join("python.exe"));
    let bundled_default = repo_root.join("tools").join("python").join("python.exe");
    if is_managed_runtime_root(repo_root) {
        return candidates
            .into_iter()
            .find(|path| path.exists())
            .unwrap_or(bundled_default)
            .display()
            .to_string();
    }
    if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
        for version in [
            "Python314",
            "Python313",
            "Python312",
            "Python311",
            "Python310",
        ] {
            candidates.push(
                PathBuf::from(&local_app_data)
                    .join("Programs")
                    .join("Python")
                    .join(version)
                    .join("python.exe"),
            );
        }
    }
    if let Ok(system_root) = env::var("SystemRoot") {
        candidates.push(PathBuf::from(system_root).join("py.exe"));
    }
    candidates
        .into_iter()
        .find(|path| path.exists())
        .map(|path| path.display().to_string())
        .unwrap_or_else(|| "py".to_string())
}

fn spawn_detached(command: Command, repo_root: &Path) -> Result<Child, String> {
    spawn_detached_with_log(
        command,
        repo_root,
        "silicium-node.out.log",
        "silicium-node.err.log",
    )
}

fn spawn_detached_with_log(
    mut command: Command,
    repo_root: &Path,
    stdout_name: &str,
    stderr_name: &str,
) -> Result<Child, String> {
    configure_detached_process(&mut command);
    let stdout = node_app_log_path(repo_root, stdout_name);
    let stderr = node_app_log_path(repo_root, stderr_name);
    if let Some(parent) = stdout.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let stdout_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(stdout)
        .map_err(|error| error.to_string())?;
    let stderr_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(stderr)
        .map_err(|error| error.to_string())?;
    command
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_file))
        .stderr(Stdio::from(stderr_file))
        .spawn()
        .map_err(|error| error.to_string())
}

#[cfg(target_os = "windows")]
fn configure_detached_process(command: &mut Command) {
    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    command.creation_flags(CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW);
}

#[cfg(not(target_os = "windows"))]
fn configure_detached_process(_command: &mut Command) {}

fn normalized_node_id(node_id: &str) -> String {
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

fn effective_node_id(node_id: &str) -> String {
    let normalized = normalized_node_id(node_id);
    if normalized == "silicium-desktop-node" {
        persistent_node_id()
    } else {
        normalized
    }
}

fn persistent_node_id() -> String {
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

fn normalize_orchestrator_url(value: &str) -> Result<String, String> {
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

fn migrate_legacy_orchestrator_url(value: &str) -> String {
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
    if legacy_hosts.iter().any(|host| lower == *host || lower == format!("{host}/orchestrator")) {
        return DEFAULT_ORCHESTRATOR_URL.to_string();
    }
    trimmed.to_string()
}

fn orchestrator_check(url: &str) -> CheckItem {
    let normalized = match normalize_orchestrator_url(url) {
        Ok(value) => value,
        Err(error) => {
            return CheckItem {
                name: "Orchestrateur".to_string(),
                ok: false,
                detail: error,
            };
        }
    };
    let health_url = format!("{}/healthz", normalized.trim_end_matches('/'));
    let curl = if cfg!(target_os = "windows") {
        "curl.exe"
    } else {
        "curl"
    };
    let mut command = Command::new(curl);
    command
        .args([
            "--fail",
            "--silent",
            "--show-error",
            "--connect-timeout",
            "5",
            "--max-time",
            "8",
        ])
        .arg(&health_url)
        .stdin(Stdio::null());
    configure_detached_process(&mut command);
    match command.output() {
        Ok(output) if output.status.success() => {
            let body = String::from_utf8_lossy(&output.stdout);
            let integrated = body.contains("\"service\":\"network_node\"");
            CheckItem {
                name: "Orchestrateur".to_string(),
                ok: integrated,
                detail: if integrated {
                    format!("{} repond avec le daemon reseau integre", normalized)
                } else {
                    format!("{} repond avec un service inattendu", normalized)
                },
            }
        }
        Ok(output) => {
            let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
            CheckItem {
                name: "Orchestrateur".to_string(),
                ok: false,
                detail: if detail.is_empty() {
                    format!("{} injoignable", normalized)
                } else {
                    format!("{} injoignable: {}", normalized, detail)
                },
            }
        }
        Err(error) => CheckItem {
            name: "Orchestrateur".to_string(),
            ok: false,
            detail: format!("verification impossible: {}", error),
        },
    }
}

fn python_command_check(repo_root: &Path) -> CheckItem {
    let python = python_launcher(repo_root);
    let mut process = Command::new(python);
    configure_python_command(&mut process, repo_root);
    process.arg("--version").stdin(Stdio::null());
    configure_detached_process(&mut process);
    match process.output() {
        Ok(output) if output.status.success() => CheckItem {
            name: "Python".to_string(),
            ok: true,
            detail: String::from_utf8_lossy(if output.stdout.is_empty() {
                &output.stderr
            } else {
                &output.stdout
            })
            .trim()
            .to_string(),
        },
        Ok(output) => CheckItem {
            name: "Python".to_string(),
            ok: false,
            detail: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        },
        Err(error) => CheckItem {
            name: "Python".to_string(),
            ok: false,
            detail: error.to_string(),
        },
    }
}

fn configure_python_command(command: &mut Command, repo_root: &Path) {
    if !cfg!(target_os = "linux") {
        return;
    }
    // AppImage's launcher exports PYTHONHOME/PYTHONPATH for its bundled
    // partial Python tree. The node uses the host interpreter with the
    // packaged third-party modules instead.
    command.env_remove("PYTHONHOME");
    let site_packages = repo_root.join("tools").join("python").join("site-packages");
    if site_packages.exists() {
        command.env("PYTHONPATH", site_packages.display().to_string());
    } else {
        command.env_remove("PYTHONPATH");
    }
}

fn identity_mode_check() -> CheckItem {
    CheckItem {
        name: "Identite reseau".to_string(),
        ok: true,
        detail: "Identite Ed25519 activee en processus - aucun openssl.exe lance".to_string(),
    }
}

fn apply_runtime_path(command: &mut Command, repo_root: &Path) {
    let mut path_entries = Vec::new();
    if is_managed_runtime_root(repo_root) {
        command.env("SILICIUM_REQUIRE_BUNDLED_RUNTIME", "1");
    }
    if cfg!(target_os = "windows") {
        let python_dir = repo_root.join("tools").join("python");
        if python_dir.exists() {
            path_entries.push(python_dir);
        }
    } else {
        let site_packages = repo_root.join("tools").join("python").join("site-packages");
        command.env_remove("PYTHONHOME");
        if site_packages.exists() {
            command.env("PYTHONPATH", site_packages.display().to_string());
        } else {
            command.env_remove("PYTHONPATH");
        }
    }
    if !path_entries.is_empty() {
        let current_path = env::var("PATH").unwrap_or_default();
        let separator = if cfg!(target_os = "windows") {
            ";"
        } else {
            ":"
        };
        let prefix = path_entries
            .iter()
            .map(|path| path.display().to_string())
            .collect::<Vec<_>>()
            .join(separator);
        let next_path = format!("{}{}{}", prefix, separator, current_path);
        command.env("PATH", next_path);
    }
}

fn apply_raytracer_env(command: &mut Command, repo_root: &Path) {
    let env_file = repo_root
        .join(".silicium")
        .join("env")
        .join("raytracer.env");
    let Ok(content) = fs::read_to_string(env_file) else {
        return;
    };
    for line in content.lines() {
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        if key == "SILICIUM_RAYTRACER_BIN" || key == "SILICIUM_RAYTRACER_ASSETS_DIR" {
            let resolved = resolve_runtime_env_path(repo_root, value);
            command.env(key, resolved);
        }
    }
}

fn resolve_runtime_env_path(repo_root: &Path, value: &str) -> PathBuf {
    let path = PathBuf::from(value.trim());
    if path.is_absolute() {
        path
    } else {
        repo_root.join(path)
    }
}

fn pid_path(repo_root: &Path) -> PathBuf {
    node_app_log_path(repo_root, "silicium-node.pid")
}

fn supervisor_pid_path(repo_root: &Path) -> PathBuf {
    node_app_log_path(repo_root, "silicium-supervisor.pid")
}

fn service_config_path(repo_root: &Path) -> PathBuf {
    node_app_log_path(repo_root, "service-config.env")
}

fn node_app_log_path(repo_root: &Path, file_name: &str) -> PathBuf {
    repo_root.join(".silicium").join("node-app").join(file_name)
}

fn write_pid(repo_root: &Path, pid: u32) -> Result<(), String> {
    let path = pid_path(repo_root);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, pid.to_string()).map_err(|error| error.to_string())
}

fn read_pid(repo_root: &Path) -> Result<Option<u32>, String> {
    let path = pid_path(repo_root);
    if !path.exists() {
        return Ok(None);
    }
    let raw = fs::read_to_string(path).map_err(|error| error.to_string())?;
    Ok(raw.trim().parse::<u32>().ok())
}

fn remove_pid(repo_root: &Path) {
    let _ = fs::remove_file(pid_path(repo_root));
}

fn read_supervisor_pid(repo_root: &Path) -> Result<Option<u32>, String> {
    let path = supervisor_pid_path(repo_root);
    if !path.exists() {
        return Ok(None);
    }
    let raw = fs::read_to_string(path).map_err(|error| error.to_string())?;
    Ok(raw.trim().parse::<u32>().ok())
}

fn claim_supervisor_pid(repo_root: &Path) -> Result<bool, String> {
    let path = supervisor_pid_path(repo_root);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let current_pid = std::process::id();
    for _ in 0..3 {
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut file) => {
                writeln!(file, "{current_pid}").map_err(|error| error.to_string())?;
                return Ok(true);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                let existing_pid = read_supervisor_pid(repo_root)?.unwrap_or(0);
                if existing_pid != current_pid && process_is_running(existing_pid) {
                    return Ok(false);
                }
                let _ = fs::remove_file(&path);
            }
            Err(error) => return Err(error.to_string()),
        }
    }
    Err("supervisor_pid_claim_retries_exhausted".to_string())
}

fn remove_supervisor_pid(repo_root: &Path) {
    let _ = fs::remove_file(supervisor_pid_path(repo_root));
}

fn cleanup_dead_pids(repo_root: &Path) {
    if read_pid(repo_root)
        .ok()
        .flatten()
        .map(|pid| !process_is_running(pid))
        .unwrap_or(false)
    {
        remove_pid(repo_root);
    }
    if read_supervisor_pid(repo_root)
        .ok()
        .flatten()
        .map(|pid| !process_is_running(pid))
        .unwrap_or(false)
    {
        remove_supervisor_pid(repo_root);
    }
}

fn write_service_config(repo_root: &Path, config: &NodeConfig) -> Result<(), String> {
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

fn read_service_config(repo_root: &Path) -> Result<NodeConfig, String> {
    let content =
        fs::read_to_string(service_config_path(repo_root)).map_err(|error| error.to_string())?;
    let mut config = NodeConfig {
        repo_root: repo_root.display().to_string(),
        orchestrator_url: DEFAULT_ORCHESTRATOR_URL.to_string(),
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

fn app_state_dir() -> PathBuf {
    if cfg!(target_os = "windows") {
        if let Ok(app_data) = env::var("APPDATA") {
            return PathBuf::from(app_data).join("SiliciumNode");
        }
        if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
            return PathBuf::from(local_app_data).join("SiliciumNode");
        }
    }
    if let Ok(home) = env::var("HOME") {
        return PathBuf::from(home).join(".config").join("silicium-node");
    }
    env::temp_dir().join("silicium-node")
}

fn global_repo_root_path() -> PathBuf {
    app_state_dir().join("repo-root.txt")
}

fn write_global_repo_root(repo_root: &Path) -> Result<(), String> {
    let path = global_repo_root_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, repo_root.display().to_string()).map_err(|error| error.to_string())
}

fn remove_global_repo_root() {
    let _ = fs::remove_file(global_repo_root_path());
}

fn cleanup_node_installation(repo_root: &Path) -> Result<(), String> {
    stop_node_processes(repo_root)?;
    uninstall_autostart_task();
    remove_global_repo_root();
    Ok(())
}

fn windows_autostart_command(executable: &Path) -> String {
    format!("\"{}\" --background", executable.display())
}

fn stop_node_processes(repo_root: &Path) -> Result<(), String> {
    if let Ok(config) = read_service_config(repo_root) {
        notify_peer_leave(&config);
    }
    if let Some(pid) = read_supervisor_pid(repo_root)? {
        let _ = kill_process_tree(pid);
    }
    if let Some(pid) = read_pid(repo_root)? {
        kill_process_tree(pid)?;
    }
    kill_known_silicium_processes(Some(repo_root));
    remove_pid(repo_root);
    remove_supervisor_pid(repo_root);
    Ok(())
}

fn cleanup_previous_node_processes(repo_root: &Path) {
    if let Ok(Some(pid)) = read_supervisor_pid(repo_root) {
        let _ = kill_process_tree(pid);
    }
    if let Ok(Some(pid)) = read_pid(repo_root) {
        let _ = kill_process_tree(pid);
    }
    kill_known_silicium_processes(Some(repo_root));
    remove_pid(repo_root);
    remove_supervisor_pid(repo_root);
}

fn notify_peer_leave(config: &NodeConfig) {
    if !cfg!(target_os = "windows") {
        return;
    }
    let url = format!(
        "{}/peers/leave",
        config.orchestrator_url.trim().trim_end_matches('/')
    );
    let node_id = normalized_node_id(&config.node_id).replace('\'', "''");
    let script = format!(
        "$body = @{{ node_id = '{node_id}' }} | ConvertTo-Json -Compress; Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Method Post -Uri '{url}' -Headers @{{ Authorization = 'Bearer demo-mesh' }} -ContentType 'application/json' -Body $body | Out-Null"
    );
    let mut command = Command::new("powershell.exe");
    command
        .arg("-NoProfile")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-Command")
        .arg(script)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    configure_detached_process(&mut command);
    let _ = command.status();
}

pub fn run_cleanup_cli() -> i32 {
    let Some(repo_root) = resolve_optional_repo_root(None) else {
        kill_known_silicium_processes(None);
        uninstall_autostart_task();
        remove_global_repo_root();
        return 0;
    };
    match cleanup_node_installation(&repo_root) {
        Ok(()) => 0,
        Err(_) => 1,
    }
}

#[cfg(not(target_os = "windows"))]
fn linux_managed_node_pids(repo_root: Option<&Path>) -> Vec<u32> {
    let root = repo_root.and_then(|path| path.canonicalize().ok());
    let root_text = root
        .as_ref()
        .map(|path| path.display().to_string())
        .unwrap_or_default();
    let mut pids = Vec::new();
    let Ok(entries) = fs::read_dir("/proc") else {
        return pids;
    };
    for entry in entries.flatten() {
        let name = entry.file_name();
        let Ok(pid) = name.to_string_lossy().parse::<u32>() else {
            continue;
        };
        if pid == std::process::id() {
            continue;
        }
        let command_line = fs::read(format!("/proc/{pid}/cmdline"))
            .ok()
            .map(|raw| {
                String::from_utf8_lossy(&raw)
                    .split('\0')
                    .filter(|part| !part.is_empty())
                    .collect::<Vec<_>>()
                    .join(" ")
            })
            .unwrap_or_default();
        let is_node_launcher = command_line.contains("start-node.sh")
            || command_line.contains("silicium node start");
        if !is_node_launcher {
            continue;
        }
        let cwd = fs::read_link(format!("/proc/{pid}/cwd")).ok();
        let in_scope = match root.as_ref() {
            Some(root) => cwd
                .as_ref()
                .map(|path| path.starts_with(root))
                .unwrap_or(false)
                || command_line.contains(&root_text),
            None => true,
        };
        if in_scope {
            pids.push(pid);
        }
    }
    pids
}

fn kill_known_silicium_processes(repo_root: Option<&Path>) {
    #[cfg(not(target_os = "windows"))]
    {
        for pid in linux_managed_node_pids(repo_root) {
            let _ = kill_process_tree(pid);
        }
        return;
    }
    #[cfg(target_os = "windows")]
    {
    let mut filters = vec![
        "$_.CommandLine -like '*silicium node start*'".to_string(),
        "$_.CommandLine -like '* --supervisor *'".to_string(),
        "$_.CommandLine -like '* --supervisor'".to_string(),
    ];
    if let Some(root) = repo_root {
        let escaped = root.display().to_string().replace('\'', "''");
        filters.push(format!("$_.CommandLine -like '*{}*'", escaped));
    }
    let filter = filters.join(" -or ");
    let script = format!(
        "Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -ne $PID -and $_.CommandLine -and ({filter}) }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
    );
    let mut command = Command::new("powershell.exe");
    command
        .arg("-NoProfile")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-Command")
        .arg(script)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    configure_detached_process(&mut command);
    let _ = command.status();
    }
}

fn kill_managed_node_processes(repo_root: &Path) {
    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(Some(pid)) = read_pid(repo_root) {
            let _ = kill_process_tree(pid);
        }
        kill_known_silicium_processes(Some(repo_root));
        return;
    }
    #[cfg(target_os = "windows")]
    {
    let escaped = repo_root.display().to_string().replace('\'', "''");
    let script = format!(
        "$root = '{escaped}'; Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.IndexOf($root, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and ($_.CommandLine.IndexOf('silicium node start', [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or $_.CommandLine.IndexOf('networked\\p2p_node', [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or $_.Name -ieq 'p2p_node.exe') }} | ForEach-Object {{ & taskkill.exe /PID $_.ProcessId /T /F | Out-Null }}"
    );
    let mut command = Command::new("powershell.exe");
    command
        .arg("-NoProfile")
        .arg("-NonInteractive")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-Command")
        .arg(script)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    configure_detached_process(&mut command);
    let _ = command.status();
    }
}

fn append_supervisor_log(repo_root: &Path, message: &str) -> Result<(), String> {
    let path = node_app_log_path(repo_root, "silicium-supervisor.err.log");
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| error.to_string())?;
    use std::io::Write;
    let now: DateTime<Utc> = SystemTime::now().into();
    let timestamp = now.to_rfc3339_opts(SecondsFormat::Secs, true);
    let normalized = message.trim_end_matches(&['\r', '\n'][..]);
    let line = format!("[{timestamp}] {normalized}\n");
    file.write_all(line.as_bytes())
        .map_err(|error| error.to_string())
}

#[cfg(target_os = "windows")]
fn process_is_running(pid: u32) -> bool {
    // Query the process directly. `tasklist` can return Access denied on
    // managed Windows installations, which previously made the UI discard
    // valid PID files and stay on the activation screen.
    unsafe {
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if handle.is_null() {
            return false;
        }
        let mut exit_code = 0_u32;
        let queried = GetExitCodeProcess(handle, &mut exit_code);
        CloseHandle(handle);
        queried != 0 && exit_code == STILL_ACTIVE as u32
    }
}

#[cfg(not(target_os = "windows"))]
fn process_is_running(pid: u32) -> bool {
    if let Ok(status) = fs::read_to_string(format!("/proc/{pid}/status")) {
        if let Some(state) = status
            .lines()
            .find(|line| line.starts_with("State:"))
            .and_then(|line| line.split_whitespace().nth(1))
        {
            return state != "Z";
        }
    }
    Command::new("kill")
        .arg("-0")
        .arg(pid.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn kill_process_tree(pid: u32) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        let mut command = Command::new("taskkill");
        command
            .arg("/PID")
            .arg(pid.to_string())
            .arg("/T")
            .arg("/F")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        configure_detached_process(&mut command);
        return command
            .status()
            .map_err(|error| error.to_string())
            .map(|_| ());
    }

    #[cfg(not(target_os = "windows"))]
    {
        let tree = linux_process_tree(pid);
        let mut first_error = None;
        for target in &tree {
            match Command::new("kill")
                .arg("-TERM")
                .arg(target.to_string())
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
            {
                Ok(_) => {}
                Err(error) if first_error.is_none() => first_error = Some(error.to_string()),
                Err(_) => {}
            }
        }
        thread::sleep(Duration::from_millis(100));
        for target in &tree {
            if !process_is_running(*target) {
                continue;
            }
            match Command::new("kill")
                .arg("-KILL")
                .arg(target.to_string())
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
            {
                Ok(_) => {}
                Err(error) if first_error.is_none() => first_error = Some(error.to_string()),
                Err(_) => {}
            }
        }
        if let Some(error) = first_error {
            Err(error)
        } else {
            Ok(())
        }
    }
}

#[cfg(not(target_os = "windows"))]
fn linux_process_tree(pid: u32) -> Vec<u32> {
    fn visit(pid: u32, seen: &mut std::collections::HashSet<u32>, result: &mut Vec<u32>) {
        if !seen.insert(pid) {
            return;
        }
        let children_path = format!("/proc/{pid}/task/{pid}/children");
        if let Ok(children) = fs::read_to_string(children_path) {
            for child in children
                .split_whitespace()
                .filter_map(|value| value.parse::<u32>().ok())
            {
                visit(child, seen, result);
            }
        }
        // Children are returned before their parent so a shell wrapper cannot
        // outlive the Python process that owns the listening socket.
        result.push(pid);
    }

    let mut result = Vec::new();
    visit(pid, &mut std::collections::HashSet::new(), &mut result);
    result
}

fn read_node_log_tail(repo_root: &Path) -> Option<String> {
    let mut parts = Vec::new();
    for (label, name) in [
        ("supervisor stderr", "silicium-supervisor.err.log"),
        ("supervisor stdout", "silicium-supervisor.out.log"),
        ("stderr", "silicium-node.err.log"),
        ("stdout", "silicium-node.out.log"),
    ] {
        let path = node_app_log_path(repo_root, name);
        let Ok(mut file) = fs::File::open(path) else {
            continue;
        };
        let mut content = String::new();
        if file.read_to_string(&mut content).is_err() {
            continue;
        }
        let tail = content
            .lines()
            .rev()
            .take(30)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect::<Vec<_>>()
            .join("\n");
        if !tail.trim().is_empty() {
            parts.push(format!("{label}:\n{tail}"));
        }
    }
    let network_export = repo_root
        .join("Network")
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node")
        .join("export");
    let claim_health = network_export.join("claim-poll.health.json");
    if let Ok(content) = fs::read_to_string(claim_health) {
        if !content.trim().is_empty() {
            parts.push(format!("scheduler claim health:\n{}", content.trim()));
        }
    }
    let claim_events = network_export.join("node.events.ndjson");
    if let Ok(content) = fs::read_to_string(claim_events) {
        let tail = content
            .lines()
            .rev()
            .filter(|line| line.contains("\"kind\":\"claim_"))
            .take(12)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect::<Vec<_>>()
            .join("\n");
        if !tail.trim().is_empty() {
            parts.push(format!("scheduler claim events:\n{tail}"));
        }
    }
    if parts.is_empty() {
        None
    } else {
        Some(parts.join("\n\n"))
    }
}

fn path_check(name: &str, path: &Path) -> CheckItem {
    CheckItem {
        name: name.to_string(),
        ok: path.exists(),
        detail: path.display().to_string(),
    }
}

fn collect_history(path: &Path, history: &mut Vec<HistoryItem>) {
    let Ok(entries) = fs::read_dir(path) else {
        return;
    };
    for entry in entries.flatten() {
        let Ok(metadata) = entry.metadata() else {
            continue;
        };
        if metadata.is_dir() {
            collect_history(&entry.path(), history);
            continue;
        }
        let modified_at = metadata
            .modified()
            .ok()
            .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
            .map(|duration| duration.as_secs())
            .unwrap_or(0);
        let Some(name) = display_history_name(&entry.path()) else {
            continue;
        };
        history.push(HistoryItem {
            name,
            modified_at,
            size_bytes: metadata.len(),
            kind: "file".to_string(),
            item_id: String::new(),
            role: String::new(),
            activity: String::new(),
            fragment_index: String::new(),
            ok: None,
            peer_id: String::new(),
        });
    }
}

fn collect_event_history(path: &Path, history: &mut Vec<HistoryItem>) {
    let Ok(raw) = fs::read_to_string(path) else {
        return;
    };
    for line in raw.lines().rev().take(500) {
        let Ok(value) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        let kind = value
            .get("kind")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim();
        let item_id = value
            .get("item_id")
            .and_then(Value::as_str)
            .unwrap_or("task")
            .trim();
        let timestamp = value
            .get("timestamp_utc")
            .and_then(Value::as_str)
            .and_then(parse_utc_timestamp)
            .unwrap_or(0);
        let duration_ms = value
            .get("duration_ms")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        let ok = value.get("ok").and_then(Value::as_bool).unwrap_or(true);
        let name = match kind {
            "task_received" | "pull_claim" => format!("task.received.{item_id}"),
            "task_started" => format!("task.started.{item_id}"),
            "fragment_fetched" => format!("fragment.fetched.{item_id}"),
            "verification_input_fetched" => format!("verification.fetched.{item_id}"),
            "task_input_fetched" => format!("task.input_fetched.{item_id}"),
            "task" | "request" if ok => format!("result.{item_id}"),
            "task" | "request" => format!("failed.{item_id}"),
            "result_return" if ok => format!("result.sent.{item_id}"),
            "result_return" => format!("result.return_failed.{item_id}"),
            _ => continue,
        };
        history.push(HistoryItem {
            name,
            modified_at: timestamp,
            size_bytes: duration_ms,
            kind: kind.to_string(),
            item_id: item_id.to_string(),
            role: value
                .get("role")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            activity: value
                .get("activity")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            fragment_index: json_value_text(value.get("fragment_index")),
            ok: value.get("ok").and_then(Value::as_bool),
            peer_id: value
                .get("source_peer")
                .or_else(|| value.get("source_node"))
                .or_else(|| value.get("target_node"))
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
        });
    }
}

fn json_value_text(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(text)) => text.clone(),
        Some(Value::Number(number)) => number.to_string(),
        Some(Value::Bool(boolean)) => boolean.to_string(),
        _ => String::new(),
    }
}

fn task_bounds(value: &Value) -> String {
    let x_start = json_value_text(value.get("x_start"));
    let x_end = json_value_text(value.get("x_end"));
    let y_start = json_value_text(value.get("y_start"));
    let y_end = json_value_text(value.get("y_end"));
    if [
        x_start.as_str(),
        x_end.as_str(),
        y_start.as_str(),
        y_end.as_str(),
    ]
    .iter()
    .any(|item| item.is_empty())
    {
        String::new()
    } else {
        format!("x {x_start}..{x_end}, y {y_start}..{y_end}")
    }
}

fn bayesian_number(value: Option<&Value>, key: &str) -> f64 {
    value
        .and_then(|item| item.get(key))
        .and_then(Value::as_f64)
        .unwrap_or(0.0)
}

fn telemetry_number(value: Option<&Value>, key: &str) -> f64 {
    value
        .and_then(|item| item.get(key))
        .and_then(Value::as_f64)
        .unwrap_or(0.0)
}

fn telemetry_u64(value: Option<&Value>, key: &str) -> u64 {
    value
        .and_then(|item| item.get(key))
        .and_then(Value::as_u64)
        .unwrap_or(0)
}

fn parse_runtime_telemetry(value: Option<&Value>) -> RuntimeTelemetry {
    RuntimeTelemetry {
        sampled_unix: telemetry_u64(value, "sampled_unix"),
        sample_interval_ms: telemetry_u64(value, "sample_interval_ms"),
        node_uptime_seconds: telemetry_number(value, "node_uptime_seconds"),
        process_cpu_percent: telemetry_number(value, "process_cpu_percent"),
        process_cpu_percent_one_core: telemetry_number(value, "process_cpu_percent_one_core"),
        process_cpu_seconds: telemetry_number(value, "process_cpu_seconds"),
        process_rss_bytes: telemetry_u64(value, "process_rss_bytes"),
        process_peak_rss_bytes: telemetry_u64(value, "process_peak_rss_bytes"),
        system_cpu_percent: telemetry_number(value, "system_cpu_percent"),
        system_memory_total_bytes: telemetry_u64(value, "system_memory_total_bytes"),
        system_memory_available_bytes: telemetry_u64(value, "system_memory_available_bytes"),
        system_memory_used_bytes: telemetry_u64(value, "system_memory_used_bytes"),
        system_memory_percent: telemetry_number(value, "system_memory_percent"),
        logical_cpu_count: telemetry_u64(value, "logical_cpu_count"),
        python_thread_count: telemetry_u64(value, "python_thread_count"),
        load_average: value
            .and_then(|item| item.get("load_average"))
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_f64)
            .collect(),
        storage_total_bytes: telemetry_u64(value, "storage_total_bytes"),
        storage_free_bytes: telemetry_u64(value, "storage_free_bytes"),
        storage_used_percent: telemetry_number(value, "storage_used_percent"),
    }
}

fn parse_resource_reputation(peer: &Value) -> Vec<BayesianResourceScore> {
    let dimensions = peer
        .get("resource_reputation")
        .and_then(|item| item.get("dimensions"))
        .and_then(Value::as_object);
    ["connection", "storage", "compute", "verify", "delegation"]
        .into_iter()
        .filter_map(|dimension| {
            let score = dimensions?.get(dimension)?;
            let combined = score.get("combined");
            Some(BayesianResourceScore {
                dimension: dimension.to_string(),
                mean: bayesian_number(combined, "mean"),
                lower_bound: bayesian_number(combined, "lower_bound"),
                evidence: bayesian_number(combined, "evidence"),
                short_term_mean: bayesian_number(score.get("short_term"), "mean"),
                long_term_mean: bayesian_number(score.get("long_term"), "mean"),
            })
        })
        .collect()
}

fn collect_machine_activity(export_dir: &Path) -> Vec<MachineActivity> {
    let snapshot_path = export_dir.join("mesh.discovery.json");
    let Ok(raw) = fs::read_to_string(snapshot_path) else {
        return Vec::new();
    };
    let Ok(snapshot) = serde_json::from_str::<Value>(&raw) else {
        return Vec::new();
    };
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    let mut machines = snapshot
        .get("peers")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|peer| {
            let node_id = peer.get("node_id")?.as_str()?.to_string();
            let last_seen = peer
                .get("last_seen_unix")
                .and_then(Value::as_u64)
                .unwrap_or(0);
            let last_claim_poll = peer
                .get("last_claim_poll_unix")
                .and_then(|value| {
                    value
                        .as_f64()
                        .or_else(|| value.as_u64().map(|item| item as f64))
                })
                .unwrap_or(0.0);
            let candidates = peer
                .get("candidates")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|candidate| {
                    Some(MachineCandidate {
                        candidate_type: candidate
                            .get("candidate_type")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        transport: candidate
                            .get("transport")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        ip: candidate
                            .get("ip")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        port: candidate.get("port").and_then(Value::as_u64).unwrap_or(0),
                        internet_routable: candidate
                            .get("internet_routable")
                            .and_then(Value::as_bool)
                            .unwrap_or(false),
                        source: candidate
                            .get("source")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                    })
                })
                .collect::<Vec<_>>();
            let transport_attestations = peer
                .get("transport_attestations")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|attestation| {
                    Some(TransportAttestation {
                        claim_hash: attestation.get("claim_hash")?.as_str()?.to_string(),
                        signature: attestation
                            .get("signature")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        route: attestation
                            .get("route")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        transport_backend: attestation
                            .get("transport_backend")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        proof_scope: attestation
                            .get("proof_scope")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        remote_peer_id: attestation
                            .get("remote_peer_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        session_id: attestation
                            .get("session_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        task_id: attestation
                            .get("task_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        content_id: attestation
                            .get("content_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        size_bytes: attestation
                            .get("size_bytes")
                            .and_then(Value::as_u64)
                            .unwrap_or(0),
                        endpoint: attestation
                            .get("endpoint")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        relay_peer_id: attestation
                            .get("relay_peer_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        peer_proof_verified: attestation
                            .get("peer_proof_verified")
                            .and_then(Value::as_bool)
                            .unwrap_or(false),
                        success: attestation
                            .get("success")
                            .and_then(Value::as_bool)
                            .unwrap_or(false),
                        failure_reason: attestation
                            .get("failure_reason")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        timestamp_unix: attestation
                            .get("timestamp_unix")
                            .and_then(Value::as_u64)
                            .unwrap_or(0),
                    })
                })
                .collect::<Vec<_>>();
            let capacity = peer.get("capacity").and_then(Value::as_object);
            let activity = peer.get("activity").and_then(Value::as_object);
            let active_tasks = activity
                .and_then(|item| item.get("active_tasks"))
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|task| {
                    Some(MachineTaskActivity {
                        item_id: task.get("item_id")?.as_str()?.to_string(),
                        role: task
                            .get("role")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        activity: task
                            .get("activity")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        workload: task
                            .get("workload")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        fragment_index: json_value_text(task.get("fragment_index")),
                        fragment_count: json_value_text(task.get("fragment_count")),
                        source_task_id: task
                            .get("source_task_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        source_node_id: task
                            .get("source_node_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        bounds: task_bounds(task),
                        phase: task
                            .get("phase")
                            .and_then(Value::as_str)
                            .unwrap_or("executing")
                            .to_string(),
                        progress_percent: telemetry_number(Some(task), "progress_percent"),
                        progress_source: task
                            .get("progress_source")
                            .and_then(Value::as_str)
                            .unwrap_or("unknown")
                            .to_string(),
                        elapsed_ms: telemetry_u64(Some(task), "elapsed_ms"),
                        eta_seconds: telemetry_number(Some(task), "eta_seconds"),
                        completed_units: telemetry_number(Some(task), "completed_units"),
                        total_units: telemetry_number(Some(task), "total_units"),
                        unit: task
                            .get("unit")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        throughput_units_per_second: telemetry_number(
                            Some(task),
                            "throughput_units_per_second",
                        ),
                        worker_threads: telemetry_u64(Some(task), "worker_threads"),
                        pixels_completed: telemetry_u64(Some(task), "pixels_completed"),
                        pixels_total: telemetry_u64(Some(task), "pixels_total"),
                        input_bytes: telemetry_u64(Some(task), "input_bytes"),
                        attempt: telemetry_u64(Some(task), "attempt"),
                        max_retries: telemetry_u64(Some(task), "max_retries"),
                        priority: task
                            .get("priority")
                            .and_then(Value::as_str)
                            .unwrap_or("normal")
                            .to_string(),
                        queued_utc: task
                            .get("queued_utc")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        resource_usage: parse_runtime_telemetry(task.get("resource_usage")),
                    })
                })
                .collect::<Vec<_>>();
            let task_queue = peer
                .get("task_queue")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|task| {
                    Some(MachineQueueItem {
                        item_id: task.get("item_id")?.as_str()?.to_string(),
                        kind: task
                            .get("kind")
                            .and_then(Value::as_str)
                            .unwrap_or("task")
                            .to_string(),
                        role: task
                            .get("role")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        activity: task
                            .get("activity")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        workload: task
                            .get("workload")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        fragment_index: json_value_text(task.get("fragment_index")),
                        fragment_count: json_value_text(task.get("fragment_count")),
                        source_task_id: task
                            .get("source_task_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        source_node_id: task
                            .get("source_node_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        status: task
                            .get("status")
                            .and_then(Value::as_str)
                            .unwrap_or("queued")
                            .to_string(),
                        priority: task
                            .get("priority")
                            .and_then(Value::as_str)
                            .unwrap_or("normal")
                            .to_string(),
                        assigned_peer_id: task
                            .get("assigned_peer_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        origin_node_id: task
                            .get("origin_node_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        bounds: task_bounds(task),
                        queued_utc: task
                            .get("queued_utc")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                    })
                })
                .collect::<Vec<_>>();
            let last_response = activity
                .and_then(|item| item.get("last_response"))
                .and_then(Value::as_object);
            Some(MachineActivity {
                node_id,
                identity_id: peer
                    .get("identity_id")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                online: last_seen > 0 && now.saturating_sub(last_seen) <= 45,
                self_node: peer.get("self").and_then(Value::as_bool).unwrap_or(false),
                scheduler_active: last_claim_poll > 0.0
                    && (now as f64 - last_claim_poll).max(0.0) <= 10.0,
                status: activity
                    .and_then(|item| item.get("status"))
                    .and_then(Value::as_str)
                    .unwrap_or(if active_tasks.is_empty() {
                        "idle"
                    } else {
                        "working"
                    })
                    .to_string(),
                roles: peer
                    .get("roles")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect(),
                app_version: peer
                    .get("app_version")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                release_channel: peer
                    .get("release_channel")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                release_build: peer
                    .get("release_build")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                http_base_url: peer
                    .get("http_base_url")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                mesh_post_url: peer
                    .get("mesh_post_url")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                relay_capable: peer
                    .get("relay_capable")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                features: peer
                    .get("features")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect(),
                candidates,
                transport_attestations,
                platform: capacity
                    .and_then(|item| item.get("platform"))
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                cpu_count: capacity
                    .and_then(|item| item.get("cpu_count"))
                    .and_then(Value::as_u64)
                    .unwrap_or(0),
                telemetry: parse_runtime_telemetry(
                    activity
                        .and_then(|item| item.get("telemetry"))
                        .or_else(|| peer.get("telemetry")),
                ),
                resource_reputation: parse_resource_reputation(peer),
                active_tasks,
                task_queue,
                last_seen_unix: last_seen,
                last_seen_utc: peer
                    .get("updated_utc")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                last_claim_poll_utc: peer
                    .get("last_claim_poll_utc")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                last_claim_error: peer
                    .get("last_claim_error")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                last_response_ok: last_response
                    .and_then(|item| item.get("ok"))
                    .and_then(Value::as_bool),
                last_response_item_id: last_response
                    .and_then(|item| item.get("item_id"))
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                last_response_utc: last_response
                    .and_then(|item| item.get("timestamp_utc"))
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
            })
        })
        .collect::<Vec<_>>();
    machines.sort_by(|left, right| {
        right
            .online
            .cmp(&left.online)
            .then_with(|| left.node_id.cmp(&right.node_id))
    });
    machines
}

fn parse_utc_timestamp(value: &str) -> Option<u64> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|datetime| datetime.with_timezone(&Utc).timestamp())
        .filter(|timestamp| *timestamp >= 0)
        .map(|timestamp| timestamp as u64)
}

fn display_history_name(path: &Path) -> Option<String> {
    let file_name = path.file_name()?.to_string_lossy();
    let lower = file_name.to_lowercase();
    if lower.ends_with(".queue.ndjson") || lower == "tasks.queue.ndjson" {
        return None;
    }
    if lower.starts_with("result.") {
        return Some(file_name.to_string());
    }
    if lower.contains("verify") || lower.contains("vote") {
        return Some(file_name.to_string());
    }
    if path
        .parent()
        .and_then(Path::file_name)
        .map(|name| name.to_string_lossy().eq_ignore_ascii_case("tasks"))
        .unwrap_or(false)
    {
        return Some(format!("task.{file_name}"));
    }
    None
}

fn directory_size(path: &Path) -> u64 {
    let Ok(entries) = fs::read_dir(path) else {
        return 0;
    };
    entries
        .flatten()
        .map(|entry| {
            let Ok(metadata) = entry.metadata() else {
                return 0;
            };
            if metadata.is_dir() {
                directory_size(&entry.path())
            } else {
                metadata.len()
            }
        })
        .sum()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    install_crash_log();
    if let Err(error) = remove_legacy_runtime_assets(&managed_runtime_root()) {
        let _ = append_app_log(&format!("legacy_runtime_cleanup_failed: {error}\n"));
    }
    thread::spawn(run_background_update_loop);
    #[cfg(target_os = "windows")]
    let background = env::args().any(|argument| argument == "--background");
    let builder = tauri::Builder::default().manage(ProcessState::default());
    #[cfg(target_os = "windows")]
    let builder = builder.setup(move |app| {
        tray::setup(app, background)?;
        Ok(())
    });
    #[cfg(target_os = "windows")]
    let builder = builder.on_window_event(|window, event| {
        if let tauri::WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            let _ = window.hide();
        }
    });
    if let Err(error) = builder
        .invoke_handler(tauri::generate_handler![
            start_node,
            stop_node,
            node_status,
            check_environment,
            install_runtime,
            node_activity,
            node_diagnostics,
            app_defaults,
            update_status,
            check_for_updates
        ])
        .run(tauri::generate_context!())
    {
        let _ = append_app_log(&format!("tauri_runtime_error: {error}\n"));
    }
}

fn install_crash_log() {
    std::panic::set_hook(Box::new(|info| {
        let _ = append_app_log(&format!("panic: {info}\n"));
    }));
}

fn append_app_log(message: &str) -> Result<(), String> {
    let path = app_state_dir().join("silicium-app.err.log");
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| error.to_string())?;
    use std::io::Write;
    file.write_all(message.as_bytes())
        .map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn node_id_is_safe_for_files_and_service_config() {
        assert_eq!(
            normalized_node_id(" pc de Thom\ninvalid "),
            "pc-de-Thom-invalid"
        );
        assert_eq!(normalized_node_id("   "), "silicium-desktop-node");
    }

    #[test]
    fn orchestrator_url_requires_http_and_a_host() {
        assert_eq!(
            normalize_orchestrator_url(" http://127.0.0.1:46100/ ").unwrap(),
            "http://127.0.0.1:46100"
        );
        assert!(normalize_orchestrator_url("127.0.0.1:46100").is_err());
        assert!(normalize_orchestrator_url("https://").is_err());
    }

    #[test]
    fn legacy_public_orchestrator_urls_migrate_to_tls_proxy() {
        for value in [
            "http://213.32.68.67:46100",
            "https://213.32.68.67:46100/",
            "http://vps-910c1dbc.vps.ovh.net:46100/orchestrator",
        ] {
            assert_eq!(
                normalize_orchestrator_url(value).unwrap(),
                DEFAULT_ORCHESTRATOR_URL
            );
        }
        assert_eq!(
            normalize_orchestrator_url("http://127.0.0.1:46100").unwrap(),
            "http://127.0.0.1:46100"
        );
    }

    #[test]
    fn current_process_is_detected_as_running() {
        assert!(process_is_running(std::process::id()));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_bundles_use_tauri_resource_layout_for_appimage_and_deb() {
        let executable = Path::new("/opt/silicium/usr/bin/silicium-node");
        let candidates = packaged_runtime_candidates(
            executable,
            Some(Path::new("/opt/silicium")),
        );

        assert!(candidates.iter().any(|candidate| {
            candidate.ends_with(Path::new("usr/lib/silicium-node/resources/runtime"))
        }));
        assert!(candidates.iter().any(|candidate| {
            candidate.ends_with(Path::new("lib/silicium-node/resources/runtime"))
        }));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_bundles_accept_tauri_product_name_resource_directory() {
        let app_dir = env::temp_dir().join(format!(
            "silicium-product-resource-layout-{}",
            std::process::id()
        ));
        let runtime = app_dir
            .join("usr")
            .join("lib")
            .join("Silicium Node")
            .join("resources")
            .join("runtime")
            .join("Network");
        let _ = fs::remove_dir_all(&app_dir);
        fs::create_dir_all(&runtime).unwrap();
        fs::write(runtime.join("silicium"), b"#!/usr/bin/env python3\n").unwrap();

        let candidates = packaged_runtime_candidates(
            Path::new("/opt/silicium/usr/bin/silicium-node"),
            Some(&app_dir),
        );

        assert!(candidates.iter().any(|candidate| {
            candidate.ends_with(Path::new("usr/lib/Silicium Node/resources/runtime"))
        }));
        assert!(candidates
            .iter()
            .any(|candidate| validate_repo_root(candidate).is_ok()));
        fs::remove_dir_all(app_dir).unwrap();
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_appimage_wrapper_ancestors_find_product_runtime_without_appdir() {
        let app_dir = env::temp_dir().join(format!(
            "silicium-appimage-wrapper-layout-{}",
            std::process::id()
        ));
        let runtime = app_dir
            .join("usr")
            .join("lib")
            .join("Silicium Node")
            .join("resources")
            .join("runtime")
            .join("Network");
        let _ = fs::remove_dir_all(&app_dir);
        fs::create_dir_all(&runtime).unwrap();
        fs::write(runtime.join("silicium"), b"#!/usr/bin/env python3\n").unwrap();

        let candidates = packaged_runtime_candidates(&app_dir.join("AppRun.wrapped"), None);

        assert!(candidates
            .iter()
            .any(|candidate| validate_repo_root(candidate).is_ok()));
        fs::remove_dir_all(app_dir).unwrap();
    }

    #[test]
    fn packaged_runtime_requires_the_network_launcher() {
        let directory = env::temp_dir().join(format!(
            "silicium-runtime-validation-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(directory.join("Network")).unwrap();
        assert_eq!(
            validate_repo_root(&directory).unwrap_err(),
            "network_runtime_not_found"
        );
        fs::write(directory.join("Network").join("silicium"), b"#!/usr/bin/env python3\n")
            .unwrap();
        assert!(validate_repo_root(&directory).is_ok());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn release_versions_keep_dev_and_prod_ordering() {
        assert!(version_is_newer("0.2.9-dev.2", "0.2.9-dev.1"));
        assert!(version_is_newer("0.2.9", "0.2.9-dev.9"));
        assert!(!version_is_newer("0.2.9-dev.1", "0.2.9"));
        assert!(!version_is_newer("0.2.9-dev.1", "0.2.9-dev.1"));
    }

    #[test]
    fn same_version_with_a_different_published_build_requires_update() {
        assert!(release_requires_update(
            "0.2.9-dev.11",
            "new-build",
            "0.2.9-dev.11",
            "old-build"
        ));
        assert!(!release_requires_update(
            "0.2.9-dev.11",
            "same-build",
            "0.2.9-dev.11",
            "same-build"
        ));
        assert!(!release_requires_update(
            "0.2.9-dev.11",
            "",
            "0.2.9-dev.11",
            "old-build"
        ));
        assert!(!release_requires_update(
            "0.2.9-dev.10",
            "other-build",
            "0.2.9-dev.11",
            "current-build"
        ));
    }

    #[test]
    fn update_install_lease_allows_only_one_installer_for_a_content_id() {
        let directory =
            env::temp_dir().join(format!("silicium-update-lease-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join("install.lock");
        assert!(acquire_install_lock_at(&path, "content-a", Duration::from_secs(60)).unwrap());
        assert!(!acquire_install_lock_at(&path, "content-a", Duration::from_secs(60)).unwrap());
        assert!(!acquire_install_lock_at(&path, "content-b", Duration::from_secs(60)).unwrap());
        fs::remove_file(&path).unwrap();
        assert!(acquire_install_lock_at(&path, "content-b", Duration::from_secs(60)).unwrap());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn managed_runtime_cleanup_removes_obsolete_build_assets() {
        let directory =
            env::temp_dir().join(format!("silicium-runtime-cleanup-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        let legacy = directory.join("tools").join("openssl").join("bin");
        let python_crypto = directory
            .join("tools")
            .join("python")
            .join("Lib")
            .join("site-packages")
            .join("cryptography");
        let obsolete_p2p_target = directory
            .join("Network")
            .join("networked")
            .join("p2p_node")
            .join("target")
            .join("release");
        let networked_runtime = directory
            .join("Network")
            .join("networked")
            .join("networked_runtime.py");
        fs::create_dir_all(&legacy).unwrap();
        fs::create_dir_all(&python_crypto).unwrap();
        fs::create_dir_all(&obsolete_p2p_target).unwrap();
        fs::write(legacy.join("openssl.exe"), b"legacy").unwrap();
        fs::write(python_crypto.join("_rust.pyd"), b"keep").unwrap();
        fs::write(obsolete_p2p_target.join("p2p_node.exe"), b"remove").unwrap();
        fs::write(&networked_runtime, b"keep").unwrap();

        remove_legacy_runtime_assets(&directory).unwrap();

        assert!(!directory.join("tools").join("openssl").exists());
        assert!(python_crypto.join("_rust.pyd").exists());
        assert!(!directory
            .join("Network")
            .join("networked")
            .join("p2p_node")
            .exists());
        assert!(networked_runtime.exists());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn missing_claim_health_is_stale_after_the_supervisor_grace_period() {
        let directory =
            env::temp_dir().join(format!("silicium-claim-health-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        assert!(!claim_poll_is_fresh(&directory, Duration::from_secs(60)));

        let health_path = claim_poll_health_path(&directory);
        fs::create_dir_all(health_path.parent().unwrap()).unwrap();
        fs::write(&health_path, b"{}").unwrap();
        assert!(claim_poll_is_fresh(&directory, Duration::from_secs(60)));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn readiness_requires_the_integrated_network_health_response() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0_u8; 512];
            let _ = stream.read(&mut request);
            stream
                .write_all(
                    b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"ok\":true,\"service\":\"network_node\"}",
                )
                .unwrap();
        });

        assert!(local_network_node_ready(port));
        server.join().unwrap();

        let unexpected_listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let unexpected_port = unexpected_listener.local_addr().unwrap().port();
        let unexpected_server = thread::spawn(move || {
            let (mut stream, _) = unexpected_listener.accept().unwrap();
            let mut request = [0_u8; 512];
            let _ = stream.read(&mut request);
            stream
                .write_all(
                    b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"ok\":true,\"service\":\"p2p_node\"}",
                )
                .unwrap();
        });
        assert!(!local_network_node_ready(unexpected_port));
        unexpected_server.join().unwrap();
    }

    #[test]
    fn legacy_runtime_cleanup_runs_for_gui_and_supervisor_startup() {
        let source = include_str!("lib.rs");
        assert!(source.contains("remove_legacy_runtime_assets(&managed_runtime_root())"));
        assert!(source.contains("remove_legacy_runtime_assets(&repo_root)"));
    }

    #[test]
    fn managed_runtime_copy_never_restores_the_legacy_openssl_cli() {
        let directory =
            env::temp_dir().join(format!("silicium-runtime-copy-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        let source = directory.join("source");
        let target = directory.join("target");
        fs::create_dir_all(source.join("tools").join("openssl").join("bin")).unwrap();
        fs::create_dir_all(source.join("Network")).unwrap();
        fs::write(
            source
                .join("tools")
                .join("openssl")
                .join("bin")
                .join("openssl.exe"),
            b"legacy",
        )
        .unwrap();
        fs::write(source.join("Network").join("silicium"), b"keep").unwrap();

        copy_dir_all(&source, &target).unwrap();

        assert!(!target.join("tools").join("openssl").exists());
        assert!(target.join("Network").join("silicium").exists());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn raytracer_env_resolves_relative_paths_from_runtime_root() {
        let directory =
            env::temp_dir().join(format!("silicium-raytracer-env-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        let env_file = directory.join(".silicium").join("env").join("raytracer.env");
        fs::create_dir_all(env_file.parent().unwrap()).unwrap();
        fs::write(
            &env_file,
            "SILICIUM_RAYTRACER_BIN=Network/bin/raytracer/silicium-raytracer\nSILICIUM_RAYTRACER_ASSETS_DIR=Network/bin/raytracer\n",
        )
        .unwrap();

        let mut command = Command::new("silicium-test");
        apply_raytracer_env(&mut command, &directory);

        let value_for = |name: &str| {
            command
                .get_envs()
                .find(|(key, _)| *key == name)
                .and_then(|(_, value)| value)
                .map(PathBuf::from)
        };
        assert_eq!(
            value_for("SILICIUM_RAYTRACER_BIN"),
            Some(
                directory
                    .join("Network")
                    .join("bin")
                    .join("raytracer")
                    .join("silicium-raytracer")
            )
        );
        assert_eq!(
            value_for("SILICIUM_RAYTRACER_ASSETS_DIR"),
            Some(directory.join("Network").join("bin").join("raytracer"))
        );
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn automatic_update_script_restarts_the_notification_shell() {
        let source = include_str!("lib.rs");
        assert!(source.contains("[string]$RepoRoot"));
        assert!(source.contains("service-config.env"));
        assert!(source.contains("notification_shell_restarted"));
        assert!(source.contains("-ArgumentList '--background'"));
        assert!(source.contains("installer_launch_retry"));
        assert!(source.contains("acquire_update_install_lock"));
        assert!(source.contains("[string]$InstallLockPath"));
        assert!(source.contains("[string]$FailurePath"));
        assert!(source.contains("update-install-failure.json"));
        assert!(source.contains("update_install_blocked"));
        assert!(source.contains("failedAtUtc"));
        assert!(source.contains("Remove-Item -LiteralPath $InstallLockPath"));
        assert!(source.contains("supervisor_recovered_after_update_failure"));
        assert!(source.contains("stale_node_runtime_stopped"));
        assert!(source.contains("Get-CimInstance Win32_Process"));
        assert!(source.contains("IndexOf('silicium node start'"));
        assert!(source.contains("kill_managed_node_processes(&repo_root)"));
    }

    #[test]
    fn windows_login_starts_the_notification_shell() {
        let command = windows_autostart_command(Path::new(r"C:\Program Files\Silicium Node.exe"));
        assert_eq!(
            command,
            r#""C:\Program Files\Silicium Node.exe" --background"#
        );
        assert!(!command.contains("--supervisor"));
    }

    #[test]
    fn update_release_requires_the_pinned_ed25519_signature() {
        let release = UpdateRelease {
            version: "0.2.9-dev.8".to_string(),
            build: "test-build".to_string(),
            channel: "dev".to_string(),
            platform: String::new(),
            url: "https://vps-910c1dbc.vps.ovh.net/downloads/silicium-node-windows-dev.exe".to_string(),
            sha256: "a".repeat(64),
            content_id: "a".repeat(64),
            signature: "sVOJv9gTgrP9GS5dcuvgvX/Ff6hsnlkguSgvnvIvZHVqD6YwP89jZzYPjuBk4eBaBGE9SkPE+ShmSnZw42XNCg==".to_string(),
            signing_key_id: UPDATE_SIGNING_KEY_ID.to_string(),
            size_bytes: 1234,
            auto_install: true,
            check_interval_seconds: 30,
        };
        assert!(validate_update_release(&release).is_ok());
        let mut tampered = release.clone();
        tampered.size_bytes += 1;
        assert_eq!(
            validate_update_release(&tampered).unwrap_err(),
            "update_signature_untrusted"
        );
    }

    #[test]
    fn update_release_platform_prevents_cross_os_installers() {
        assert!(update_platform_matches(&update_platform()));
        assert!(!update_platform_matches("unsupported-test-platform"));
        assert_eq!(update_platform_matches(""), cfg!(target_os = "windows"));
    }

    #[test]
    fn failed_update_is_blocked_only_for_the_same_artifact() {
        let release = UpdateRelease {
            version: "0.2.9".to_string(),
            build: "build-a".to_string(),
            channel: "prod".to_string(),
            platform: String::new(),
            url: String::new(),
            sha256: String::new(),
            content_id: "content-a".to_string(),
            signature: String::new(),
            signing_key_id: String::new(),
            size_bytes: 0,
            auto_install: true,
            check_interval_seconds: 0,
        };
        let failure = UpdateInstallFailure {
            content_id: "content-a".to_string(),
            version: release.version.clone(),
            build: release.build.clone(),
            error: "installer_exit_1".to_string(),
            failed_at_utc: current_utc(),
        };
        assert!(update_install_failure_matches(&failure, &release));
        let mut new_release = release.clone();
        new_release.content_id = "content-b".to_string();
        assert!(!update_install_failure_matches(&failure, &new_release));
    }

    #[test]
    fn update_artifact_hash_is_portable() {
        let path = env::temp_dir().join(format!(
            "silicium-update-hash-{}-{}.bin",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::write(&path, b"abc").unwrap();
        assert_eq!(
            sha256_file(&path).unwrap(),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn machine_activity_reads_work_and_last_response() {
        let directory =
            env::temp_dir().join(format!("silicium-machine-activity-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(&directory).unwrap();
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();
        fs::write(
            directory.join("mesh.discovery.json"),
            format!(
                r#"{{"peers":[{{"node_id":"worker-a","roles":["compute"],"app_version":"0.2.9-dev.1","release_channel":"dev","release_build":"test","last_seen_unix":{now},"last_claim_poll_unix":{now},"last_claim_poll_utc":"2026-07-13T18:00:00Z","last_claim_error":"","updated_utc":"2026-07-13T18:00:00Z","activity":{{"status":"working","active_tasks":[{{"item_id":"render:1","role":"compute","activity":"fragment","workload":"raytracer-fragment","fragment_index":3,"fragment_count":16,"x_start":0,"x_end":100,"y_start":0,"y_end":100}}],"last_response":{{"item_id":"verify:2","ok":true,"timestamp_utc":"2026-07-13T17:59:00Z"}}}},"task_queue":[{{"item_id":"verify:3","kind":"task","role":"verify","activity":"verify","workload":"verification/rendering/raytracer-fragment","fragment_index":3,"fragment_count":16,"source_task_id":"render:1","source_node_id":"worker-b","status":"queued","priority":"high","assigned_peer_id":"","origin_node_id":"orchestrator-1","x_start":0,"x_end":100,"y_start":0,"y_end":100}}]}}]}}"#
            ),
        )
        .unwrap();

        let machines = collect_machine_activity(&directory);
        assert_eq!(machines.len(), 1);
        assert!(machines[0].online);
        assert!(machines[0].scheduler_active);
        assert_eq!(machines[0].status, "working");
        assert_eq!(machines[0].app_version, "0.2.9-dev.1");
        assert_eq!(machines[0].release_channel, "dev");
        assert_eq!(machines[0].active_tasks[0].fragment_index, "3");
        assert_eq!(machines[0].active_tasks[0].fragment_count, "16");
        assert_eq!(machines[0].active_tasks[0].bounds, "x 0..100, y 0..100");
        assert_eq!(machines[0].task_queue[0].role, "verify");
        assert_eq!(machines[0].task_queue[0].source_node_id, "worker-b");
        assert_eq!(machines[0].last_response_ok, Some(true));
        let _ = fs::remove_dir_all(&directory);
    }

    #[test]
    fn runtime_telemetry_parser_preserves_resource_metrics() {
        let payload: Value = serde_json::json!({
            "sampled_unix": 1_784_000_000_u64,
            "node_uptime_seconds": 42.5,
            "process_cpu_percent": 37.25,
            "process_rss_bytes": 134_217_728_u64,
            "system_cpu_percent": 68.5,
            "system_memory_total_bytes": 17_179_869_184_u64,
            "system_memory_used_bytes": 8_589_934_592_u64,
            "system_memory_percent": 50.0,
            "logical_cpu_count": 16_u64,
            "python_thread_count": 7_u64,
            "storage_used_percent": 61.2
        });
        let telemetry = parse_runtime_telemetry(Some(&payload));
        assert_eq!(telemetry.sampled_unix, 1_784_000_000);
        assert_eq!(telemetry.process_rss_bytes, 134_217_728);
        assert_eq!(telemetry.logical_cpu_count, 16);
        assert_eq!(telemetry.python_thread_count, 7);
        assert!((telemetry.process_cpu_percent - 37.25).abs() < f64::EPSILON);
        assert!((telemetry.system_memory_percent - 50.0).abs() < f64::EPSILON);
    }
}
