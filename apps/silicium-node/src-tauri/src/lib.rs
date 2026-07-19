use chrono::{DateTime, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    env,
    fs::{self, OpenOptions},
    io::Read,
    net::{TcpStream, ToSocketAddrs, UdpSocket},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::State;

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
const CLAIM_POLL_STALE_AFTER: Duration = Duration::from_secs(20);

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
    online: bool,
    scheduler_active: bool,
    status: String,
    roles: Vec<String>,
    active_tasks: Vec<MachineTaskActivity>,
    last_seen_utc: String,
    last_claim_poll_utc: String,
    last_claim_error: String,
    last_response_ok: Option<bool>,
    last_response_item_id: String,
    last_response_utc: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct MachineTaskActivity {
    item_id: String,
    role: String,
    activity: String,
    workload: String,
    fragment_index: String,
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
    let supervisor_running = root
        .as_ref()
        .and_then(|root| read_supervisor_pid(root).ok().flatten())
        .map(process_is_running)
        .unwrap_or(false);
    let port_ready = root.is_some() && TcpStream::connect(("127.0.0.1", 46101)).is_ok();
    let running = node_running || supervisor_running || port_ready;
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
    config.orchestrator_url = normalize_orchestrator_url(&config.orchestrator_url)?;
    let repo_root = resolve_repo_root(&config.repo_root)?;
    validate_repo_root(&repo_root)?;
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
    write_supervisor_pid(&repo_root, child.id())?;
    wait_for_supervised_node_start(&mut child, &repo_root, 46101)?;
    drop(child);
    *node = None;
    if let Some(warning) = autostart_warning {
        Ok(format!(
            "Silicium node started, but Windows autostart is not installed yet: {warning}"
        ))
    } else {
        Ok(format!(
            "Silicium local service started with compute,verify roles against {}",
            config.orchestrator_url
        ))
    }
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
        command_check("Python", &python_launcher(&root), &["--version"]),
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
    } else {
        let script = root
            .join("deploy")
            .join("linux")
            .join("install-vps-deps.sh");
        if !script.exists() {
            return Err(format!("installer_not_found: {}", script.display()));
        }
        Command::new("bash")
            .arg(script)
            .current_dir(&root)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
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
    let port_ready = TcpStream::connect(("127.0.0.1", 46101)).is_ok();
    let orchestrator_url = read_service_config(&root)
        .map(|config| config.orchestrator_url)
        .unwrap_or_else(|_| "https://vps-910c1dbc.vps.ovh.net/orchestrator".to_string());
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
        python: command_check("Python", &python_launcher(&root), &["--version"]),
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
            .unwrap_or_else(|| "https://vps-910c1dbc.vps.ovh.net/orchestrator".to_string()),
        node_id: saved_config
            .map(|config| effective_node_id(&config.node_id))
            .unwrap_or_else(persistent_node_id),
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
    if !repo_root.join("Network").exists() {
        return Err("network_directory_not_found".to_string());
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
        validate_repo_root(&root)?;
        return Ok(root);
    }

    copy_dir_all(&source, &root)?;
    validate_repo_root(&root)?;
    Ok(root)
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
    let mut candidates = Vec::new();
    if let Ok(exe) = env::current_exe() {
        if let Some(parent) = exe.parent() {
            candidates.push(parent.join("runtime"));
            candidates.push(parent.join("resources").join("runtime"));
            candidates.push(parent.join("..").join("Resources").join("runtime"));
        }
    }
    candidates.push(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("resources")
            .join("runtime"),
    );

    candidates
        .into_iter()
        .find(|path| validate_repo_root(path).is_ok())
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
            .arg("--export-dir")
            .arg(".silicium\\networked\\silicium-desktop-node\\export")
            .arg("--state-dir")
            .arg(".silicium\\networked\\silicium-desktop-node\\state")
            .arg("--peer-http-bind")
            .arg("0.0.0.0")
            .arg("--peer-http-port")
            .arg("46101")
            .arg("--peer-advertise-host")
            .arg(&advertise_host)
            .arg("--peer-advertise-port")
            .arg("46101")
            .arg("--seed-peers")
            .arg(&config.orchestrator_url)
            .arg("--nat-punch-enable")
            .arg("--p2p-direct-transport-backend")
            .arg("auto")
            .arg("--mesh-key")
            .arg("demo-mesh")
            .arg("--reputation-score")
            .arg(config.reputation_score.to_string())
            .arg("--idle-ms")
            .arg("250")
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
            .arg("--nat-punch-enable")
            .arg("--p2p-direct-transport-backend")
            .arg("auto")
            .current_dir(repo_root);
        apply_runtime_path(&mut command, repo_root);
        spawn_detached(command, repo_root)
    }
}

fn wait_for_supervised_node_start(
    supervisor: &mut Child,
    repo_root: &Path,
    port: u16,
) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(12);
    loop {
        if let Some(status) = supervisor.try_wait().map_err(|error| error.to_string())? {
            remove_supervisor_pid(repo_root);
            let logs = read_node_log_tail(repo_root);
            return Err(format!(
                "supervisor_exited_before_ready: {status}\n{}",
                logs.unwrap_or_else(|| "No supervisor logs available yet.".to_string())
            ));
        }
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(());
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

fn spawn_supervisor(repo_root: &Path) -> Result<Child, String> {
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
    if !cfg!(target_os = "windows") {
        return Ok(());
    }
    let exe = env::current_exe().map_err(|error| error.to_string())?;
    let task_command = format!(
        "\"{}\" --supervisor --repo-root \"{}\"",
        exe.display(),
        repo_root.display()
    );
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
    let Ok(repo_root) = resolve_repo_root_readonly(&repo_root) else {
        return 2;
    };
    if validate_repo_root(&repo_root).is_err() {
        return 2;
    }
    let _ = write_supervisor_pid(&repo_root, std::process::id());
    let config = read_service_config(&repo_root).unwrap_or_else(|_| NodeConfig {
        repo_root: repo_root.display().to_string(),
        orchestrator_url: "https://vps-910c1dbc.vps.ovh.net/orchestrator".to_string(),
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
        let port_ready = TcpStream::connect(("127.0.0.1", 46101)).is_ok();
        let mut node_running = pid_running || port_ready;
        if node_running
            && node_started_at.elapsed() >= CLAIM_POLL_STALE_AFTER
            && !claim_poll_is_fresh(&repo_root, CLAIM_POLL_STALE_AFTER)
        {
            let _ = append_supervisor_log(
                &repo_root,
                "claim_poll_stale: restarting the managed network node",
            );
            if let Ok(Some(pid)) = read_pid(&repo_root) {
                let _ = kill_process_tree(pid);
            } else {
                kill_known_silicium_processes(Some(&repo_root));
            }
            remove_pid(&repo_root);
            node_running = false;
            thread::sleep(Duration::from_secs(1));
        }
        if node_running {
            restart_attempts = 0;
        }
        if !node_running {
            remove_pid(&repo_root);
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
                    let _ =
                        append_supervisor_log(&repo_root, &format!("spawn_node_failed: {error}\n"));
                }
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
    fs::metadata(claim_poll_health_path(repo_root))
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
    let trimmed = value.trim().trim_end_matches('/');
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
    let secure = normalized.starts_with("https://");
    let authority = normalized
        .split_once("://")
        .map(|(_, rest)| rest)
        .unwrap_or_default()
        .split('/')
        .next()
        .unwrap_or_default();
    let address = if authority.contains(':') {
        authority.to_string()
    } else {
        format!("{}:{}", authority, if secure { 443 } else { 80 })
    };
    let reachable = address
        .to_socket_addrs()
        .ok()
        .and_then(|mut addresses| {
            addresses
                .any(|socket| {
                    TcpStream::connect_timeout(&socket, Duration::from_millis(800)).is_ok()
                })
                .then_some(())
        })
        .is_some();
    CheckItem {
        name: "Orchestrateur".to_string(),
        ok: reachable,
        detail: if reachable {
            format!("{} joignable", normalized)
        } else {
            format!("{} injoignable", normalized)
        },
    }
}

fn command_check(name: &str, command: &str, args: &[&str]) -> CheckItem {
    let mut process = Command::new(command);
    process.args(args).stdin(Stdio::null());
    configure_detached_process(&mut process);
    match process.output() {
        Ok(output) if output.status.success() => CheckItem {
            name: name.to_string(),
            ok: true,
            detail: String::from_utf8_lossy(&output.stdout).trim().to_string(),
        },
        Ok(output) => CheckItem {
            name: name.to_string(),
            ok: false,
            detail: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        },
        Err(error) => CheckItem {
            name: name.to_string(),
            ok: false,
            detail: error.to_string(),
        },
    }
}

fn identity_mode_check() -> CheckItem {
    CheckItem {
        name: "Identite reseau".to_string(),
        ok: true,
        detail: "HMAC demo actif - OpenSSL non requis".to_string(),
    }
}

fn find_openssl(repo_root: Option<&Path>) -> Option<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(root) = repo_root {
        candidates.push(
            root.join("tools")
                .join("openssl")
                .join("bin")
                .join("openssl.exe"),
        );
        candidates.push(root.join("tools").join("openssl").join("openssl.exe"));
        candidates.push(root.join("bin").join("openssl").join("openssl.exe"));
        if is_managed_runtime_root(root) {
            return candidates.into_iter().find(|path| path.exists());
        }
    }
    if cfg!(target_os = "windows") {
        candidates.extend([
            PathBuf::from(r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe"),
            PathBuf::from(r"C:\Program Files\OpenSSL-Win32\bin\openssl.exe"),
            PathBuf::from(r"C:\Program Files\Git\usr\bin\openssl.exe"),
            PathBuf::from(r"C:\Program Files (x86)\OpenSSL-Win32\bin\openssl.exe"),
            PathBuf::from(r"C:\Program Files (x86)\Git\usr\bin\openssl.exe"),
        ]);
    } else {
        candidates.extend([
            PathBuf::from("/usr/bin/openssl"),
            PathBuf::from("/usr/local/bin/openssl"),
        ]);
    }
    candidates.into_iter().find(|path| path.exists())
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
    }
    if let Some(openssl_bin) = find_openssl(Some(repo_root)) {
        command.env("SILICIUM_OPENSSL_BIN", &openssl_bin);
        if let Some(openssl_dir) = openssl_bin.parent() {
            if let Some(openssl_root) = openssl_dir.parent() {
                path_entries.push(openssl_root.to_path_buf());
                let modules_dir = openssl_root.join("lib").join("ossl-modules");
                if modules_dir.exists() {
                    command.env("OPENSSL_MODULES", modules_dir);
                } else {
                    let bin_modules_dir = openssl_dir.join("ossl-modules");
                    if bin_modules_dir.exists() {
                        command.env("OPENSSL_MODULES", bin_modules_dir);
                    }
                }
            }
            path_entries.push(openssl_dir.to_path_buf());
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

fn write_supervisor_pid(repo_root: &Path, pid: u32) -> Result<(), String> {
    let path = supervisor_pid_path(repo_root);
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
        orchestrator_url: "https://vps-910c1dbc.vps.ovh.net/orchestrator".to_string(),
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
    uninstall_autostart_task();
    remove_global_repo_root();
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

fn kill_known_silicium_processes(repo_root: Option<&Path>) {
    if !cfg!(target_os = "windows") {
        return;
    }
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
    let status = if cfg!(target_os = "windows") {
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
        command.status()
    } else {
        Command::new("kill")
            .arg(pid.to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
    };
    status.map_err(|error| error.to_string()).map(|_| ())
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
            role: value.get("role").and_then(Value::as_str).unwrap_or("").to_string(),
            activity: value.get("activity").and_then(Value::as_str).unwrap_or("").to_string(),
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
            let last_seen = peer.get("last_seen_unix").and_then(Value::as_u64).unwrap_or(0);
            let last_claim_poll = peer
                .get("last_claim_poll_unix")
                .and_then(|value| value.as_f64().or_else(|| value.as_u64().map(|item| item as f64)))
                .unwrap_or(0.0);
            let activity = peer.get("activity").and_then(Value::as_object);
            let active_tasks = activity
                .and_then(|item| item.get("active_tasks"))
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|task| {
                    Some(MachineTaskActivity {
                        item_id: task.get("item_id")?.as_str()?.to_string(),
                        role: task.get("role").and_then(Value::as_str).unwrap_or("").to_string(),
                        activity: task.get("activity").and_then(Value::as_str).unwrap_or("").to_string(),
                        workload: task.get("workload").and_then(Value::as_str).unwrap_or("").to_string(),
                        fragment_index: json_value_text(task.get("fragment_index")),
                    })
                })
                .collect::<Vec<_>>();
            let last_response = activity
                .and_then(|item| item.get("last_response"))
                .and_then(Value::as_object);
            Some(MachineActivity {
                node_id,
                online: last_seen > 0 && now.saturating_sub(last_seen) <= 45,
                scheduler_active: last_claim_poll > 0.0
                    && (now as f64 - last_claim_poll).max(0.0) <= 10.0,
                status: activity
                    .and_then(|item| item.get("status"))
                    .and_then(Value::as_str)
                    .unwrap_or(if active_tasks.is_empty() { "idle" } else { "working" })
                    .to_string(),
                roles: peer
                    .get("roles")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect(),
                active_tasks,
                last_seen_utc: peer.get("updated_utc").and_then(Value::as_str).unwrap_or("").to_string(),
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
                last_response_ok: last_response.and_then(|item| item.get("ok")).and_then(Value::as_bool),
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
    machines.sort_by(|left, right| right.online.cmp(&left.online).then_with(|| left.node_id.cmp(&right.node_id)));
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
    if let Err(error) = tauri::Builder::default()
        .manage(ProcessState::default())
        .invoke_handler(tauri::generate_handler![
            start_node,
            stop_node,
            node_status,
            check_environment,
            install_runtime,
            node_activity,
            node_diagnostics,
            app_defaults
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
    fn current_process_is_detected_as_running() {
        assert!(process_is_running(std::process::id()));
    }

    #[test]
    fn machine_activity_reads_work_and_last_response() {
        let directory = env::temp_dir().join(format!("silicium-machine-activity-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(&directory).unwrap();
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
        fs::write(
            directory.join("mesh.discovery.json"),
            format!(
                r#"{{"peers":[{{"node_id":"worker-a","roles":["compute"],"last_seen_unix":{now},"last_claim_poll_unix":{now},"last_claim_poll_utc":"2026-07-13T18:00:00Z","last_claim_error":"","updated_utc":"2026-07-13T18:00:00Z","activity":{{"status":"working","active_tasks":[{{"item_id":"render:1","role":"compute","activity":"fragment","workload":"raytracer-fragment","fragment_index":3}}],"last_response":{{"item_id":"verify:2","ok":true,"timestamp_utc":"2026-07-13T17:59:00Z"}}}}}}]}}"#
            ),
        )
        .unwrap();

        let machines = collect_machine_activity(&directory);
        assert_eq!(machines.len(), 1);
        assert!(machines[0].online);
        assert!(machines[0].scheduler_active);
        assert_eq!(machines[0].status, "working");
        assert_eq!(machines[0].active_tasks[0].fragment_index, "3");
        assert_eq!(machines[0].last_response_ok, Some(true));
        let _ = fs::remove_dir_all(&directory);
    }
}
