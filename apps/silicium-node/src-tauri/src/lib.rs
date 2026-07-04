use serde::{Deserialize, Serialize};
use std::{
    env,
    fs,
    net::UdpSocket,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::UNIX_EPOCH,
};
use tauri::State;

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
fn node_status(state: State<ProcessState>) -> Result<NodeStatus, String> {
    let node = state
        .node
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    Ok(NodeStatus {
        running: node.is_some(),
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

    let child = spawn_node(&repo_root, &config)?;
    *node = Some(child);
    Ok(format!(
        "Silicium node started with compute,verify roles against {}",
        config.orchestrator_url
    ))
}

#[tauri::command]
fn stop_node(state: State<ProcessState>) -> Result<String, String> {
    let mut node = state
        .node
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    let Some(mut child) = node.take() else {
        return Ok("Silicium node is not running".to_string());
    };
    child.kill().map_err(|error| error.to_string())?;
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
        command_check("OpenSSL", "openssl", &["version"]),
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
        let script = repo_root
            .join("Network")
            .join("demo")
            .join("networked")
            .join("start-node.cmd");
        if !script.exists() {
            return Err(format!("script_not_found: {}", script.display()));
        }
        let node_id = normalized_node_id(&config.node_id);
        let mut command = Command::new("cmd");
        command
            .arg("/C")
            .arg(script)
            .arg(node_id)
            .arg("compute,verify")
            .arg("46101")
            .arg(&config.orchestrator_url)
            .arg(&advertise_host)
            .arg("demo-mesh")
            .arg(config.reputation_score.to_string())
            .current_dir(repo_root);
        spawn_detached(command)
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
        spawn_detached(command)
    }
}

fn detect_local_ip() -> Option<String> {
    let socket = UdpSocket::bind("0.0.0.0:0").ok()?;
    socket.connect("8.8.8.8:80").ok()?;
    Some(socket.local_addr().ok()?.ip().to_string())
}

fn spawn_detached(mut command: Command) -> Result<Child, String> {
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| error.to_string())
}

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
