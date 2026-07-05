use serde::{Deserialize, Serialize};
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

#[derive(Debug, Deserialize)]
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
fn node_status(repo_root: Option<String>, state: State<ProcessState>) -> Result<NodeStatus, String> {
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

    let running = repo_root
        .as_deref()
        .and_then(|root| resolve_repo_root(root).ok())
        .and_then(|root| read_pid(&root).ok().flatten())
        .map(process_is_running)
        .unwrap_or(false);

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
    if let Some(pid) = read_pid(&repo_root)? {
        if process_is_running(pid) {
            return Ok("Silicium node already running in background".to_string());
        }
        remove_pid(&repo_root);
    }

    let mut child = spawn_node(&repo_root, &config)?;
    write_pid(&repo_root, child.id())?;
    wait_for_node_start(&mut child, &repo_root, 46101)?;
    *node = Some(child);
    Ok(format!(
        "Silicium node started with compute,verify roles against {}",
        config.orchestrator_url
    ))
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

    let root = repo_root
        .as_deref()
        .and_then(|value| resolve_repo_root(value).ok())
        .or_else(discover_repo_root);
    if let Some(root) = root {
        if let Some(pid) = read_pid(&root)? {
            kill_process_tree(pid)?;
        }
        remove_pid(&root);
    }

    Ok("Silicium node stopped".to_string())
}

#[tauri::command]
fn check_environment(repo_root: String) -> Result<Vec<CheckItem>, String> {
    let root = resolve_repo_root(&repo_root)?;
    let mut checks = vec![
        command_check("Git", "git", &["--version"]),
        command_check("Node.js", "node", &["--version"]),
        command_check("npm", if cfg!(target_os = "windows") { "npm.cmd" } else { "npm" }, &["--version"]),
        command_check("Python", if cfg!(target_os = "windows") { "py" } else { "python3" }, &["--version"]),
        openssl_check(),
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
        Command::new("cmd")
            .arg("/C")
            .arg(script)
            .arg("-SkipDockerCheck")
            .current_dir(&root)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
    } else {
        let script = root.join("deploy").join("linux").join("install-vps-deps.sh");
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
    let networked_dir = root.join("Network").join(".silicium").join("networked");
    let mut history = Vec::new();
    collect_history(&networked_dir, &mut history);
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
    AppDefaults {
        repo_root: discover_repo_root()
            .map(|path| path.display().to_string())
            .unwrap_or_default(),
        advertise_host: detect_local_ip().unwrap_or_else(|| "127.0.0.1".to_string()),
        orchestrator_url: "http://213.32.68.67:46100".to_string(),
    }
}

fn resolve_repo_root(repo_root: &str) -> Result<PathBuf, String> {
    if !repo_root.trim().is_empty() {
        return Ok(PathBuf::from(repo_root.trim()));
    }
    discover_repo_root().ok_or_else(|| "repo_root_not_found".to_string())
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
            return Err(format!("silicium_cli_not_found: {}", silicium_cli.display()));
        }
        let node_id = normalized_node_id(&config.node_id);
        let mut command = Command::new("py");
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
            .arg("--reputation-score")
            .arg(config.reputation_score.to_string())
            .arg("--idle-ms")
            .arg("250")
            .current_dir(&network_root);
        apply_raytracer_env(&mut command, repo_root);
        apply_runtime_path(&mut command);
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
            .current_dir(repo_root);
        apply_runtime_path(&mut command);
        spawn_detached(command, repo_root)
    }
}

fn wait_for_node_start(child: &mut Child, repo_root: &Path, port: u16) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_secs(8);
    loop {
        if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
            remove_pid(repo_root);
            let logs = read_node_log_tail(repo_root);
            return Err(format!(
                "node_exited_before_ready: {status}\n{}",
                logs.unwrap_or_else(|| "No node logs available yet.".to_string())
            ));
        }
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(());
        }
        if Instant::now() >= deadline {
            let logs = read_node_log_tail(repo_root);
            return Err(format!(
                "node_not_ready_after_timeout\n{}",
                logs.unwrap_or_else(|| "No node logs available yet.".to_string())
            ));
        }
        thread::sleep(Duration::from_millis(250));
    }
}

fn detect_local_ip() -> Option<String> {
    let socket = UdpSocket::bind("0.0.0.0:0").ok()?;
    socket.connect("8.8.8.8:80").ok()?;
    Some(socket.local_addr().ok()?.ip().to_string())
}

fn spawn_detached(mut command: Command, repo_root: &Path) -> Result<Child, String> {
    configure_detached_process(&mut command);
    let stdout = node_app_log_path(repo_root, "silicium-node.out.log");
    let stderr = node_app_log_path(repo_root, "silicium-node.err.log");
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
    const DETACHED_PROCESS: u32 = 0x0000_0008;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    command.creation_flags(CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_NO_WINDOW);
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
    match Command::new(command)
        .args(args)
        .stdin(Stdio::null())
        .output()
    {
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

fn openssl_check() -> CheckItem {
    if let Some(path) = find_openssl() {
        let path_string = path.display().to_string();
        let mut check = command_check("OpenSSL", &path_string, &["version"]);
        if check.ok {
            check.detail = format!("{} ({})", check.detail, path.display());
        }
        return check;
    }
    command_check("OpenSSL", "openssl", &["version"])
}

fn find_openssl() -> Option<PathBuf> {
    let candidates = if cfg!(target_os = "windows") {
        vec![
            PathBuf::from(r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe"),
            PathBuf::from(r"C:\Program Files\OpenSSL-Win32\bin\openssl.exe"),
            PathBuf::from(r"C:\Program Files\Git\usr\bin\openssl.exe"),
            PathBuf::from(r"C:\Program Files (x86)\OpenSSL-Win32\bin\openssl.exe"),
            PathBuf::from(r"C:\Program Files (x86)\Git\usr\bin\openssl.exe"),
        ]
    } else {
        vec![PathBuf::from("/usr/bin/openssl"), PathBuf::from("/usr/local/bin/openssl")]
    };
    candidates.into_iter().find(|path| path.exists())
}

fn apply_runtime_path(command: &mut Command) {
    if let Some(openssl) = find_openssl().and_then(|path| path.parent().map(Path::to_path_buf)) {
        let current_path = env::var("PATH").unwrap_or_default();
        let separator = if cfg!(target_os = "windows") { ";" } else { ":" };
        let next_path = format!("{}{}{}", openssl.display(), separator, current_path);
        command.env("PATH", next_path);
    }
}

fn apply_raytracer_env(command: &mut Command, repo_root: &Path) {
    let env_file = repo_root.join(".silicium").join("env").join("raytracer.env");
    let Ok(content) = fs::read_to_string(env_file) else {
        return;
    };
    for line in content.lines() {
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        if key == "SILICIUM_RAYTRACER_BIN" || key == "SILICIUM_RAYTRACER_ASSETS_DIR" {
            command.env(key, value);
        }
    }
}

fn pid_path(repo_root: &Path) -> PathBuf {
    node_app_log_path(repo_root, "silicium-node.pid")
}

fn node_app_log_path(repo_root: &Path, file_name: &str) -> PathBuf {
    repo_root
        .join(".silicium")
        .join("node-app")
        .join(file_name)
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

fn process_is_running(pid: u32) -> bool {
    if cfg!(target_os = "windows") {
        Command::new("cmd")
            .arg("/C")
            .arg(format!("tasklist /FI \"PID eq {pid}\" /NH"))
            .stdin(Stdio::null())
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
        Command::new("taskkill")
            .arg("/PID")
            .arg(pid.to_string())
            .arg("/T")
            .arg("/F")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
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
        history.push(HistoryItem {
            name: entry.file_name().to_string_lossy().to_string(),
            modified_at,
            size_bytes: metadata.len(),
        });
    }
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
