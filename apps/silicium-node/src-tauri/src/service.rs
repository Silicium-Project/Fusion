//! Background service and autostart: Windows scheduled task / Run key,
//! Linux autostart entry, and the service controls used by the tray menu.

use crate::*;

#[cfg(target_os = "windows")]
pub(crate) fn start_configured_node_service() -> Result<String, String> {
    let repo_root = resolve_repo_root_readonly("")?;
    validate_repo_root(&repo_root)?;
    read_service_config(&repo_root).map_err(|_| "node_not_configured".to_string())?;
    install_autostart_task(&repo_root)?;
    cleanup_dead_pids(&repo_root);

    if read_supervisor_pid(&repo_root)?
        .map(process_is_running)
        .unwrap_or(false)
    {
        if wait_for_existing_node_start(&repo_root, NODE_API_PORT) {
            return Ok("Le service Silicium est deja demarre.".to_string());
        }
        cleanup_previous_node_processes(&repo_root);
    }

    let mut child = spawn_supervisor(&repo_root)?;
    wait_for_supervised_node_start(&mut child, &repo_root, NODE_API_PORT)?;
    drop(child);
    Ok("Le service Silicium est demarre.".to_string())
}

#[cfg(target_os = "windows")]
pub(crate) fn migrate_configured_node_autostart() -> Result<(), String> {
    let repo_root = resolve_repo_root_readonly("")?;
    validate_repo_root(&repo_root)?;
    read_service_config(&repo_root).map_err(|_| "node_not_configured".to_string())?;
    install_autostart_task(&repo_root)
}

#[cfg(target_os = "windows")]
pub(crate) fn stop_configured_node_service() -> Result<String, String> {
    let repo_root = resolve_repo_root_readonly("")?;
    stop_node_processes(&repo_root)?;
    Ok("Le service Silicium est arrete jusqu'au prochain demarrage manuel.".to_string())
}

#[cfg(target_os = "windows")]
pub(crate) fn restart_configured_node_service() -> Result<String, String> {
    let repo_root = resolve_repo_root_readonly("")?;
    read_service_config(&repo_root).map_err(|_| "node_not_configured".to_string())?;
    stop_node_processes(&repo_root)?;
    thread::sleep(Duration::from_millis(500));
    start_configured_node_service()?;
    Ok("Le service Silicium a ete redemarre.".to_string())
}

#[cfg(target_os = "windows")]
pub(crate) fn configured_node_service_running() -> bool {
    let Some(repo_root) = resolve_optional_repo_root(None) else {
        return false;
    };
    cleanup_dead_pids(&repo_root);
    local_network_node_ready(NODE_API_PORT)
}

pub(crate) fn install_autostart_task(repo_root: &Path) -> Result<(), String> {
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

pub(crate) fn install_linux_autostart(repo_root: &Path) -> Result<(), String> {
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

pub(crate) fn linux_autostart_executable() -> Result<PathBuf, String> {
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

pub(crate) fn install_autostart_run_key(task_command: &str) -> Result<(), String> {
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

pub(crate) fn uninstall_autostart_task() {
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

pub(crate) fn windows_autostart_command(executable: &Path) -> String {
    format!("\"{}\" --background", executable.display())
}
