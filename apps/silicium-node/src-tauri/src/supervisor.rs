//! Supervisor mode (`--supervisor`): keeps the node running, restarts it when
//! the claim poll goes stale, and logs to the supervisor log.

use crate::*;

pub fn run_supervisor_cli() -> i32 {
    let mut repo_root = String::new();
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--repo-root" {
            repo_root = args.next().unwrap_or_default();
        }
    }
    // The supervisor is also the Linux autostart entrypoint. It must refresh
    // the persistent runtime from the currently mounted AppImage before it
    // starts the network child; using the readonly resolver here left an old
    // start-node.sh in ~/.config after an AppImage update.
    let repo_root = match resolve_repo_root(&repo_root) {
        Ok(root) => root,
        Err(error) => {
            let _ = append_app_log(&format!("supervisor_start_failed: {error}\n"));
            return 2;
        }
    };
    if let Err(error) = remove_legacy_runtime_assets(&repo_root) {
        let _ = append_supervisor_log(
            &repo_root,
            &format!("legacy_runtime_cleanup_failed: {error}\n"),
        );
    }
    if validate_repo_root(&repo_root).is_err() {
        return 2;
    }
    match claim_supervisor_pid(&repo_root) {
        Ok(true) => {}
        Ok(false) => return 0,
        Err(error) => {
            let _ =
                append_supervisor_log(&repo_root, &format!("supervisor_lease_failed: {error}\n"));
            return 2;
        }
    }
    // A supervisor launched directly by XDG autostart does not pass through
    // spawn_supervisor(), so the previous session's Python traceback would
    // otherwise remain in the diagnostic tail after a successful recovery.
    // Reset only after taking the lease: a second supervisor must never wipe
    // logs belonging to the active one.
    if let Err(error) = reset_node_session_logs(&repo_root) {
        let _ = append_supervisor_log(&repo_root, &format!("session_log_reset_failed: {error}\n"));
    }
    // An older updater may have lost silicium-node.pid while leaving the
    // Python network runtime alive. Replace it on supervisor startup so the
    // advertised app version/build always matches this executable.
    kill_managed_node_processes(&repo_root);
    remove_pid(&repo_root);
    thread::spawn(run_background_update_loop);
    let config = read_service_config(&repo_root).unwrap_or_else(|_| NodeConfig {
        repo_root: repo_root.display().to_string(),
        orchestrator_url: DEFAULT_ORCHESTRATOR_URL.to_string(),
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
        let mut node_running = pid_running;
        if node_running
            && node_started_at.elapsed() >= CLAIM_POLL_STALE_AFTER
            && !local_network_node_ready(46101)
            && !claim_poll_is_fresh(&repo_root, CLAIM_POLL_STALE_AFTER)
        {
            let _ = append_supervisor_log(
                &repo_root,
                "claim_poll_stale: restarting the managed network node",
            );
            if let Ok(Some(pid)) = read_pid(&repo_root) {
                let _ = kill_process_tree(pid);
            }
            // Older Linux bundles tracked the shell wrapper instead of the
            // Python child. Reap both the recorded tree and any orphaned
            // managed launcher before trying to bind the node port again.
            kill_known_silicium_processes(Some(&repo_root));
            remove_pid(&repo_root);
            node_running = false;
            let _ = wait_for_local_port_release(46101, Duration::from_secs(2));
        }
        if node_running {
            restart_attempts = 0;
        }
        if !node_running {
            remove_pid(&repo_root);
            kill_known_silicium_processes(Some(&repo_root));
            if wait_for_local_port_release(46101, Duration::from_secs(2)) {
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
                        let _ = append_supervisor_log(
                            &repo_root,
                            &format!("spawn_node_failed: {error}\n"),
                        );
                    }
                }
            } else {
                restart_attempts = restart_attempts.saturating_add(1);
                let _ = append_supervisor_log(
                    &repo_root,
                    "node_port_occupied: waiting before retrying managed network node",
                );
            }
        }
        let delay = if restart_attempts > 3 { 20 } else { 5 };
        thread::sleep(Duration::from_secs(delay));
    }
}

pub(crate) fn claim_poll_health_path(repo_root: &Path) -> PathBuf {
    repo_root
        .join("Network")
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node")
        .join("export")
        .join("claim-poll.health.json")
}

pub(crate) fn claim_poll_is_fresh(repo_root: &Path, maximum_age: Duration) -> bool {
    let path = claim_poll_health_path(repo_root);
    if !path.exists() {
        // The caller already applies a bootstrap grace period. Beyond it, a
        // missing file means that the scheduler pull loop never became live.
        return false;
    }
    fs::metadata(path)
        .and_then(|metadata| metadata.modified())
        .ok()
        .and_then(|modified| SystemTime::now().duration_since(modified).ok())
        .map(|age| age <= maximum_age)
        .unwrap_or(false)
}

pub(crate) fn detect_local_ip() -> Option<String> {
    let socket = UdpSocket::bind("0.0.0.0:0").ok()?;
    socket.connect("8.8.8.8:80").ok()?;
    Some(socket.local_addr().ok()?.ip().to_string())
}

pub(crate) fn append_supervisor_log(repo_root: &Path, message: &str) -> Result<(), String> {
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
