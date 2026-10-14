//! Files owned by the app: PID files, application state directory and the
//! global repository-root pointer.

use crate::*;

pub(crate) fn pid_path(repo_root: &Path) -> PathBuf {
    node_app_log_path(repo_root, "silicium-node.pid")
}

pub(crate) fn supervisor_pid_path(repo_root: &Path) -> PathBuf {
    node_app_log_path(repo_root, "silicium-supervisor.pid")
}

pub(crate) fn service_config_path(repo_root: &Path) -> PathBuf {
    node_app_log_path(repo_root, "service-config.env")
}

pub(crate) fn node_app_log_path(repo_root: &Path, file_name: &str) -> PathBuf {
    repo_root.join(".silicium").join("node-app").join(file_name)
}

pub(crate) fn write_pid(repo_root: &Path, pid: u32) -> Result<(), String> {
    let path = pid_path(repo_root);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, pid.to_string()).map_err(|error| error.to_string())
}

pub(crate) fn read_pid(repo_root: &Path) -> Result<Option<u32>, String> {
    let path = pid_path(repo_root);
    if !path.exists() {
        return Ok(None);
    }
    let raw = fs::read_to_string(path).map_err(|error| error.to_string())?;
    Ok(raw.trim().parse::<u32>().ok())
}

pub(crate) fn remove_pid(repo_root: &Path) {
    let _ = fs::remove_file(pid_path(repo_root));
}

pub(crate) fn read_supervisor_pid(repo_root: &Path) -> Result<Option<u32>, String> {
    let path = supervisor_pid_path(repo_root);
    if !path.exists() {
        return Ok(None);
    }
    let raw = fs::read_to_string(path).map_err(|error| error.to_string())?;
    Ok(raw.trim().parse::<u32>().ok())
}

pub(crate) fn claim_supervisor_pid(repo_root: &Path) -> Result<bool, String> {
    let path = supervisor_pid_path(repo_root);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let current_pid = std::process::id();
    for _ in 0..3 {
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut file) => {
                writeln!(file, "{current_pid}").map_err(|error| error.to_string())?;
                return Ok(true);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                let existing_pid = read_supervisor_pid(repo_root)?.unwrap_or(0);
                if existing_pid != current_pid && process_is_running(existing_pid) {
                    return Ok(false);
                }
                let _ = fs::remove_file(&path);
            }
            Err(error) => return Err(error.to_string()),
        }
    }
    Err("supervisor_pid_claim_retries_exhausted".to_string())
}

pub(crate) fn remove_supervisor_pid(repo_root: &Path) {
    let _ = fs::remove_file(supervisor_pid_path(repo_root));
}

pub(crate) fn cleanup_dead_pids(repo_root: &Path) {
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

pub(crate) fn app_state_dir() -> PathBuf {
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

pub(crate) fn global_repo_root_path() -> PathBuf {
    app_state_dir().join("repo-root.txt")
}

pub(crate) fn write_global_repo_root(repo_root: &Path) -> Result<(), String> {
    let path = global_repo_root_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, repo_root.display().to_string()).map_err(|error| error.to_string())
}

pub(crate) fn remove_global_repo_root() {
    let _ = fs::remove_file(global_repo_root_path());
}
