//! Starting the network node process: spawn, readiness checks, session logs,
//! Rust node/compute-daemon launchers and detached child processes.

use crate::*;

pub(crate) const NODE_API_PORT: u16 = 9092;

fn runtime_binary(repo_root: &Path, name: &str) -> PathBuf {
    let suffix = if cfg!(target_os = "windows") {
        ".exe"
    } else {
        ""
    };
    repo_root
        .join("Network")
        .join("bin")
        .join(format!("{name}{suffix}"))
}

fn runtime_work_dir(repo_root: &Path) -> PathBuf {
    repo_root
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node")
        .join("work")
}

fn runtime_state_dir(repo_root: &Path) -> PathBuf {
    repo_root
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node")
        .join("state")
}

fn runtime_export_dir(repo_root: &Path) -> PathBuf {
    repo_root
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node")
        .join("export")
}

fn spawn_compute_daemon(repo_root: &Path) -> Result<(), String> {
    let binary = runtime_binary(repo_root, "compute_daemon");
    if !binary.is_file() {
        return Err(format!("compute_daemon_not_found: {}", binary.display()));
    }
    fs::create_dir_all(runtime_work_dir(repo_root)).map_err(|error| error.to_string())?;
    let mut command = Command::new(binary);
    command
        .current_dir(repo_root)
        .env("SILICIUM_DATA_DIR", runtime_state_dir(repo_root))
        .env("SILICIUM_COMPUTE_ROOT", runtime_work_dir(repo_root))
        .env("SILICIUM_COMPUTE_BIND", "127.0.0.1:9090")
        .env(
            "SILICIUM_RAYTRACER_BIN",
            repo_root
                .join("Network")
                .join("bin")
                .join("raytracer")
                .join(if cfg!(target_os = "windows") {
                    "silicium-raytracer.exe"
                } else {
                    "silicium-raytracer"
                }),
        );
    command.env(
        "SILICIUM_RAYTRACER_ASSETS_DIR",
        repo_root.join("Network").join("bin").join("raytracer"),
    );
    apply_raytracer_env(&mut command, repo_root);
    apply_runtime_path(&mut command, repo_root);
    spawn_detached_with_log(
        command,
        repo_root,
        "silicium-compute.out.log",
        "silicium-compute.err.log",
    )
    .map(|_| ())
}

pub(crate) fn spawn_node(repo_root: &Path, config: &NodeConfig) -> Result<Child, String> {
    let binary = runtime_binary(repo_root, "p2p_node");
    if !binary.is_file() {
        return Err(format!("p2p_node_not_found: {}", binary.display()));
    }
    spawn_compute_daemon(repo_root)?;
    let node_id = effective_node_id(&config.node_id);
    let export_dir = runtime_export_dir(repo_root);
    let state_dir = runtime_state_dir(repo_root);
    let work_dir = runtime_work_dir(repo_root);
    fs::create_dir_all(&export_dir).map_err(|error| error.to_string())?;
    fs::create_dir_all(&state_dir).map_err(|error| error.to_string())?;
    let bootstrap = env::var("SILICIUM_BOOTSTRAP_PEERS")
        .or_else(|_| env::var("SILICIUM_NODE_BOOTSTRAP_PEERS"))
        .unwrap_or_else(|_| default_node_bootstrap_peers().to_string());
    let p2p_port = env::var("SILICIUM_NODE_P2P_PORT").unwrap_or_else(|_| "0".to_string());
    let mut command = Command::new(binary);
    command
        .current_dir(repo_root)
        .env("SILICIUM_NODE_ID", &node_id)
        .env("SILICIUM_NODE_ROLES", "compute,verify")
        .env("SILICIUM_APP_VERSION", release_version())
        .env("SILICIUM_RELEASE_CHANNEL", release_channel())
        .env("SILICIUM_RELEASE_BUILD", release_build())
        .env("SILICIUM_DATA_DIR", &state_dir)
        .env("SILICIUM_COMPUTE_ROOT", &work_dir)
        .env("SILICIUM_WORKLOAD_STORAGE_DIR", work_dir.join("jobs"))
        .env("SILICIUM_EXPORT_DIR", &export_dir)
        .env("SILICIUM_API_BIND", "127.0.0.1")
        .env("API_PORT", NODE_API_PORT.to_string())
        .env("SILICIUM_P2P_PORT", p2p_port)
        .env("SILICIUM_BOOTSTRAP_PEERS", bootstrap)
        // Tasks are only executed when signed by a trusted publisher: the
        // orchestrator pinned in the bootstrap address (`/p2p/<peer id>`).
        // Results are verified by another worker, or by the worker itself when
        // it is the only one on the network (node defaults).
        .env("SILICIUM_WORK_OWN_TASKS", "1")
        .env("COMPUTE_DAEMON_URL", "http://127.0.0.1:9090");
    apply_runtime_path(&mut command, repo_root);
    spawn_detached(command, repo_root)
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
        && response.contains("\"service\":\"p2p_node\"")
        && response.contains("\"status\":\"ok\"")
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
        "silicium-compute.out.log",
        "silicium-compute.err.log",
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
