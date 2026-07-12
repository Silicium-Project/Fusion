use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    env,
    fs::{self, OpenOptions},
    io::Read,
    net::{TcpStream, UdpSocket},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant, UNIX_EPOCH},
};
use tauri::State;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[derive(Default)]
struct ProcessState {
    node: Mutex<Option<Child>>,
}

const SUPERVISOR_TASK_NAME: &str = "SiliciumNodeService";
const SUPERVISOR_RUN_KEY_NAME: &str = "SiliciumNodeService";

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
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct HistoryItem {
    name: String,
    modified_at: u64,
    size_bytes: u64,
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
    let port_ready = TcpStream::connect(("127.0.0.1", 46101)).is_ok();
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
fn start_node(config: NodeConfig, state: State<ProcessState>) -> Result<String, String> {
    let mut node = state
        .node
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    if node.is_some() {
        return Ok("Silicium node already running".to_string());
    }

    let repo_root = resolve_repo_root(&config.repo_root)?;
    validate_repo_root(&repo_root)?;
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
    *node = Some(child);
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
        openssl_check(Some(&root)),
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
    let root = resolve_repo_root(&repo_root)?;
    validate_repo_root(&root)?;
    let networked_dir = root
        .join("Network")
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node");
    let mut history = Vec::new();
    collect_event_history(&networked_dir.join("export").join("node.events.ndjson"), &mut history);
    if history.is_empty() {
        collect_history(&networked_dir, &mut history);
    }
    history.sort_by(|left, right| right.modified_at.cmp(&left.modified_at));
    history.truncate(12);
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
    let storage_bytes = directory_size(&networked_dir);

    Ok(NodeActivity {
        known_results,
        known_tasks,
        last_result,
        storage_bytes,
        history,
    })
}

#[tauri::command]
fn app_defaults() -> AppDefaults {
    let repo_root = discover_configured_repo_root()
        .or_else(discover_repo_root)
        .or_else(discover_managed_runtime_root)
        .map(|path| path.display().to_string())
        .unwrap_or_default();
    AppDefaults {
        repo_root,
        advertise_host: detect_local_ip().unwrap_or_else(|| "127.0.0.1".to_string()),
        orchestrator_url: "http://213.32.68.67:46100".to_string(),
    }
}

fn resolve_optional_repo_root(repo_root: Option<&str>) -> Option<PathBuf> {
    repo_root
        .filter(|value| !value.trim().is_empty())
        .and_then(|value| resolve_repo_root(value).ok())
        .or_else(discover_configured_repo_root)
        .or_else(discover_repo_root)
}

fn resolve_repo_root(repo_root: &str) -> Result<PathBuf, String> {
    if !repo_root.trim().is_empty() {
        return refresh_managed_runtime_if_needed(PathBuf::from(repo_root.trim()));
    }
    if let Some(root) = discover_configured_repo_root() {
        return refresh_managed_runtime_if_needed(root);
    }
    discover_repo_root()
        .or_else(discover_managed_runtime_root)
        .map(refresh_managed_runtime_if_needed)
        .unwrap_or_else(ensure_managed_runtime)
}

fn discover_repo_root() -> Option<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(current_dir) = env::current_dir() {
        candidates.push(current_dir);
    }
    candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));

    for candidate in candidates {
        for ancestor in candidate.ancestors() {
            if ancestor.join("Network").exists() && ancestor.join("Site").exists() {
                return Some(ancestor.to_path_buf());
            }
        }
    }
    None
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
        let node_id = normalized_node_id(&config.node_id);
        let mut command = Command::new(python_launcher(repo_root));
        command
            .arg("silicium")
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
            .arg("--mesh-key")
            .arg("demo-mesh")
            .arg("--pull-tasks-enable")
            .arg("--pull-tasks-interval-s")
            .arg("2")
            .arg("--reputation-score")
            .arg(config.reputation_score.to_string())
            .arg("--idle-ms")
            .arg("250")
            .current_dir(&network_root);
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
            .arg(normalized_node_id(&config.node_id))
            .arg("compute,verify")
            .arg("46101")
            .arg(&config.orchestrator_url)
            .arg(&advertise_host)
            .arg("demo-mesh")
            .arg(config.reputation_score.to_string())
            .arg("--pull-tasks-enable")
            .arg("--pull-tasks-interval-s")
            .arg("2")
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
    let Ok(repo_root) = resolve_repo_root(&repo_root) else {
        return 2;
    };
    if validate_repo_root(&repo_root).is_err() {
        return 2;
    }
    let _ = write_supervisor_pid(&repo_root, std::process::id());
    let config = read_service_config(&repo_root).unwrap_or_else(|_| NodeConfig {
        repo_root: repo_root.display().to_string(),
        orchestrator_url: "http://213.32.68.67:46100".to_string(),
        advertise_host: detect_local_ip().unwrap_or_else(|| "127.0.0.1".to_string()),
        node_id: "silicium-desktop-node".to_string(),
        reputation_score: 100,
    });

    let mut restart_attempts = 0_u32;
    loop {
        cleanup_dead_pids(&repo_root);
        let pid_running = read_pid(&repo_root)
            .ok()
            .flatten()
            .map(process_is_running)
            .unwrap_or(false);
        let port_ready = TcpStream::connect(("127.0.0.1", 46101)).is_ok();
        let node_running = pid_running || port_ready;
        if node_running {
            restart_attempts = 0;
        }
        if !node_running {
            remove_pid(&repo_root);
            match spawn_node(&repo_root, &config) {
                Ok(child) => {
                    restart_attempts = restart_attempts.saturating_add(1);
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
    if node_id.trim().is_empty() {
        "silicium-desktop-node".to_string()
    } else {
        node_id.trim().to_string()
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

fn openssl_check(repo_root: Option<&Path>) -> CheckItem {
    if let Some(path) = find_openssl(repo_root) {
        let path_string = path.display().to_string();
        let mut check = command_check("OpenSSL", &path_string, &["version"]);
        if check.ok {
            check.detail = format!("{} ({})", check.detail, path.display());
        }
        return check;
    }
    command_check("OpenSSL", "openssl", &["version"])
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
    if cfg!(target_os = "windows") {
        let python_dir = repo_root.join("tools").join("python");
        if python_dir.exists() {
            path_entries.push(python_dir);
        }
    }
    if let Some(openssl) =
        find_openssl(Some(repo_root)).and_then(|path| path.parent().map(Path::to_path_buf))
    {
        if let Some(parent) = openssl.parent() {
            path_entries.push(parent.to_path_buf());
        }
        path_entries.push(openssl);
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
        orchestrator_url: "http://213.32.68.67:46100".to_string(),
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

fn read_global_repo_root() -> Option<PathBuf> {
    let raw = fs::read_to_string(global_repo_root_path()).ok()?;
    let path = PathBuf::from(raw.trim());
    if validate_repo_root(&path).is_ok() {
        Some(path)
    } else {
        None
    }
}

fn remove_global_repo_root() {
    let _ = fs::remove_file(global_repo_root_path());
}

fn discover_configured_repo_root() -> Option<PathBuf> {
    read_global_repo_root()
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
    file.write_all(message.as_bytes())
        .map_err(|error| error.to_string())
}

fn process_is_running(pid: u32) -> bool {
    if cfg!(target_os = "windows") {
        let mut command = Command::new("cmd");
        command
            .arg("/C")
            .arg(format!("tasklist /FI \"PID eq {pid}\" /NH"))
            .stdin(Stdio::null());
        configure_detached_process(&mut command);
        command
            .output()
            .map(|output| {
                output.status.success()
                    && String::from_utf8_lossy(&output.stdout).contains(&pid.to_string())
            })
            .unwrap_or(false)
    } else {
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
        });
    }
}

fn collect_event_history(path: &Path, history: &mut Vec<HistoryItem>) {
    let Ok(raw) = fs::read_to_string(path) else {
        return;
    };
    for line in raw.lines().rev().take(80) {
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
        let duration_ms = value.get("duration_ms").and_then(Value::as_u64).unwrap_or(0);
        let ok = value.get("ok").and_then(Value::as_bool).unwrap_or(true);
        let name = match kind {
            "task_received" | "pull_claim" => format!("task.received.{item_id}"),
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
        });
    }
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
    tauri::Builder::default()
        .manage(ProcessState::default())
        .invoke_handler(tauri::generate_handler![
            start_node,
            stop_node,
            node_status,
            check_environment,
            install_runtime,
            node_activity,
            app_defaults
        ])
        .run(tauri::generate_context!())
        .expect("error while running Silicium Node");
}
