//! Stopping and cleaning up node processes (`--cleanup`), process liveness
//! and process-tree termination on Windows and Linux.

use crate::*;

pub(crate) fn cleanup_node_installation(repo_root: &Path) -> Result<(), String> {
    stop_node_processes(repo_root)?;
    uninstall_autostart_task();
    remove_global_repo_root();
    Ok(())
}

pub(crate) fn stop_node_processes(repo_root: &Path) -> Result<(), String> {
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

pub(crate) fn cleanup_previous_node_processes(repo_root: &Path) {
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

pub(crate) fn notify_peer_leave(config: &NodeConfig) {
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
pub(crate) fn linux_managed_node_pids(repo_root: Option<&Path>) -> Vec<u32> {
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
        let is_node_launcher =
            command_line.contains("start-node.sh") || command_line.contains("silicium node start");
        if !is_node_launcher {
            continue;
        }
        let cwd = fs::read_link(format!("/proc/{pid}/cwd")).ok();
        let in_scope = match root.as_ref() {
            Some(root) => {
                cwd.as_ref()
                    .map(|path| path.starts_with(root))
                    .unwrap_or(false)
                    || command_line.contains(&root_text)
            }
            None => true,
        };
        if in_scope {
            pids.push(pid);
        }
    }
    pids
}

pub(crate) fn kill_known_silicium_processes(repo_root: Option<&Path>) {
    #[cfg(not(target_os = "windows"))]
    {
        for pid in linux_managed_node_pids(repo_root) {
            let _ = kill_process_tree(pid);
        }
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

pub(crate) fn kill_managed_node_processes(repo_root: &Path) {
    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(Some(pid)) = read_pid(repo_root) {
            let _ = kill_process_tree(pid);
        }
        kill_known_silicium_processes(Some(repo_root));
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

#[cfg(target_os = "windows")]
pub(crate) fn process_is_running(pid: u32) -> bool {
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
pub(crate) fn process_is_running(pid: u32) -> bool {
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

pub(crate) fn kill_process_tree(pid: u32) -> Result<(), String> {
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
pub(crate) fn linux_process_tree(pid: u32) -> Vec<u32> {
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
