//! Tauri commands invoked by the frontend (`invoke(...)`). They are registered
//! in [`crate::run`].

use crate::*;

#[tauri::command]
pub fn node_status(
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
    let node_ready = root.is_some() && local_network_node_ready(NODE_API_PORT);
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
pub fn start_node(mut config: NodeConfig, state: State<ProcessState>) -> Result<String, String> {
    let mut node = state
        .node
        .lock()
        .map_err(|_| "process_state_locked".to_string())?;
    if node.is_some() {
        return Ok("Silicium node already running".to_string());
    }

    config.node_id = effective_node_id(&config.node_id);
    if config.orchestrator_url.trim().is_empty() {
        config.orchestrator_url = default_orchestrator_url().to_string();
    }
    config.orchestrator_url = migrate_legacy_orchestrator_url(&config.orchestrator_url);
    config.orchestrator_url = normalize_orchestrator_url(&config.orchestrator_url)?;
    let repo_root = resolve_repo_root(&config.repo_root)?;
    validate_repo_root(&repo_root)?;
    cleanup_dead_pids(&repo_root);
    if local_network_node_ready(NODE_API_PORT) {
        return Ok("Silicium node already running in background".to_string());
    }
    let managed_process_starting = read_supervisor_pid(&repo_root)?
        .map(process_is_running)
        .unwrap_or(false)
        || read_pid(&repo_root)?
            .map(process_is_running)
            .unwrap_or(false);
    if managed_process_starting && wait_for_existing_node_start(&repo_root, NODE_API_PORT) {
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
    wait_for_supervised_node_start(&mut child, &repo_root, NODE_API_PORT)?;
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

#[tauri::command]
pub fn stop_node(repo_root: Option<String>, state: State<ProcessState>) -> Result<String, String> {
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
pub fn check_environment(repo_root: String) -> Result<Vec<CheckItem>, String> {
    let root = resolve_repo_root(&repo_root)?;
    let mut checks = vec![identity_mode_check()];

    checks.push(path_check("Repo Silicium", &root.join("Network")));
    checks.push(path_check(
        "Raytracer runtime",
        &root.join(".silicium").join("env").join("raytracer.env"),
    ));
    Ok(checks)
}

#[tauri::command]
pub fn node_activity(repo_root: String) -> Result<NodeActivity, String> {
    let root = resolve_repo_root_readonly(&repo_root)?;
    validate_repo_root(&root)?;
    // Activity journal and peer files written by the node.
    let networked_dir = runtime_node_dir(&root);
    let mut history = Vec::new();
    collect_event_history(
        &networked_dir.join("export").join("node.events.ndjson"),
        &mut history,
    );
    history.sort_by_key(|entry| std::cmp::Reverse(entry.modified_at));
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
pub fn node_diagnostics(repo_root: String) -> Result<NodeDiagnostics, String> {
    let root = resolve_repo_root_readonly(&repo_root)?;
    validate_repo_root(&root)?;
    cleanup_dead_pids(&root);
    let node_pid = read_pid(&root).ok().flatten();
    let supervisor_pid = read_supervisor_pid(&root).ok().flatten();
    let node_running = node_pid.map(process_is_running).unwrap_or(false);
    let supervisor_running = supervisor_pid.map(process_is_running).unwrap_or(false);
    let port_ready = local_network_node_ready(NODE_API_PORT);
    let orchestrator_url = read_service_config(&root)
        .map(|config| config.orchestrator_url)
        .unwrap_or_else(|_| default_orchestrator_url().to_string());
    let log_dir = node_app_log_path(&root, "silicium-node.err.log")
        .parent()
        .map(|path| path.display().to_string())
        .unwrap_or_else(|| root.display().to_string());
    Ok(NodeDiagnostics {
        repo_root: root.display().to_string(),
        log_dir,
        node_pid,
        supervisor_pid,
        node_running,
        supervisor_running,
        port_ready,
        orchestrator: orchestrator_check(&orchestrator_url),
        openssl: identity_mode_check(),
        log_tail: read_node_log_tail(&root)
            .unwrap_or_else(|| "Aucun log node disponible pour le moment.".to_string()),
    })
}

#[tauri::command]
pub fn app_defaults() -> AppDefaults {
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
            .unwrap_or_else(|| default_orchestrator_url().to_string()),
        node_id: saved_config
            .map(|config| effective_node_id(&config.node_id))
            .unwrap_or_else(persistent_node_id),
    }
}

#[tauri::command]
pub fn update_status() -> UpdateStatus {
    read_update_status().unwrap_or_else(default_update_status)
}

#[tauri::command]
pub fn check_for_updates() -> UpdateStatus {
    check_for_update_once(false)
}
