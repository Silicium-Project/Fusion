use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
};
use tauri::State;

#[derive(Default)]
struct ProcessState {
    children: Mutex<HashMap<String, Child>>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct NodeConfig {
    role: String,
    repo_root: String,
    orchestrator_url: String,
    advertise_host: String,
    node_id: String,
    reputation_score: u16,
}

#[derive(Debug, Serialize)]
struct NodeStatus {
    worker: bool,
    verifier: bool,
}

#[tauri::command]
fn node_status(state: State<ProcessState>) -> Result<NodeStatus, String> {
    let children = state
        .children
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    Ok(NodeStatus {
        worker: children.contains_key("worker"),
        verifier: children.contains_key("verifier"),
    })
}

#[tauri::command]
fn start_node(config: NodeConfig, state: State<ProcessState>) -> Result<String, String> {
    let role = normalize_role(&config.role)?;
    let mut children = state
        .children
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    if children.contains_key(role) {
        return Ok(format!("{role} already running"));
    }

    let repo_root = PathBuf::from(config.repo_root.trim());
    validate_repo_root(&repo_root)?;

    let child = spawn_node(&repo_root, role, &config)?;
    children.insert(role.to_string(), child);
    Ok(format!("{role} started against {}", config.orchestrator_url))
}

#[tauri::command]
fn stop_node(role: String, state: State<ProcessState>) -> Result<String, String> {
    let role = normalize_role(&role)?;
    let mut children = state
        .children
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    let Some(mut child) = children.remove(role) else {
        return Ok(format!("{role} is not running"));
    };
    child.kill().map_err(|error| error.to_string())?;
    Ok(format!("{role} stopped"))
}

fn normalize_role(role: &str) -> Result<&'static str, String> {
    match role.trim().to_ascii_lowercase().as_str() {
        "worker" => Ok("worker"),
        "verifier" => Ok("verifier"),
        _ => Err("unsupported_role".to_string()),
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

fn spawn_node(repo_root: &Path, role: &str, config: &NodeConfig) -> Result<Child, String> {
    if cfg!(target_os = "windows") {
        let script = repo_root
            .join("Network")
            .join("scripts")
            .join(if role == "worker" {
                "start-worker.cmd"
            } else {
                "start-verifier.cmd"
            });
        if !script.exists() {
            return Err(format!("script_not_found: {}", script.display()));
        }
        let mut command = Command::new("cmd");
        command
            .arg("/C")
            .arg(script)
            .arg(&config.orchestrator_url)
            .arg(&config.advertise_host)
            .current_dir(repo_root)
            .env(
                "SILICIUM_NODE_ID",
                if config.node_id.trim().is_empty() {
                    format!("{role}-desktop-1")
                } else {
                    config.node_id.clone()
                },
            )
            .env("SILICIUM_REPUTATION_SCORE", config.reputation_score.to_string());
        spawn_detached(command)
    } else {
        let script = repo_root.join("deploy").join("linux").join("start-node.sh");
        if !script.exists() {
            return Err(format!("script_not_found: {}", script.display()));
        }
        let node_role = if role == "worker" { "compute" } else { "verify" };
        let port = if role == "worker" { "46101" } else { "46102" };
        let node_id = if config.node_id.trim().is_empty() {
            format!("{role}-desktop-1")
        } else {
            config.node_id.clone()
        };
        let mut command = Command::new("bash");
        command
            .arg(script)
            .arg(node_id)
            .arg(node_role)
            .arg(port)
            .arg(&config.orchestrator_url)
            .arg(&config.advertise_host)
            .arg("demo-mesh")
            .arg(config.reputation_score.to_string())
            .current_dir(repo_root);
        spawn_detached(command)
    }
}

fn spawn_detached(mut command: Command) -> Result<Child, String> {
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| error.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(ProcessState::default())
        .invoke_handler(tauri::generate_handler![start_node, stop_node, node_status])
        .run(tauri::generate_context!())
        .expect("error while running Silicium Node");
}
