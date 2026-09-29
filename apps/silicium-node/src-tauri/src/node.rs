//! Starting the network node process: spawn, readiness checks, session logs,
//! Python launcher selection and detached child processes.

use crate::*;

pub(crate) fn spawn_node(repo_root: &Path, config: &NodeConfig) -> Result<Child, String> {
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

pub(crate) fn wait_for_supervised_node_start(
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

pub(crate) fn wait_for_existing_node_start(repo_root: &Path, port: u16) -> bool {
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

pub(crate) fn local_network_node_ready(port: u16) -> bool {
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

pub(crate) fn wait_for_local_port_release(port: u16, timeout: Duration) -> bool {
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

pub(crate) fn reset_node_session_logs(repo_root: &Path) -> Result<(), String> {
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

pub(crate) fn spawn_supervisor(repo_root: &Path) -> Result<Child, String> {
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

pub(crate) fn python_launcher(repo_root: &Path) -> String {
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

pub(crate) fn spawn_detached(command: Command, repo_root: &Path) -> Result<Child, String> {
    spawn_detached_with_log(
        command,
        repo_root,
        "silicium-node.out.log",
        "silicium-node.err.log",
    )
}

pub(crate) fn spawn_detached_with_log(
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
pub(crate) fn configure_detached_process(command: &mut Command) {
    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    command.creation_flags(CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW);
}

#[cfg(not(target_os = "windows"))]
pub(crate) fn configure_detached_process(_command: &mut Command) {}
