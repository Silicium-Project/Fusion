//! Self-update: release identity, update status and lock files, and the
//! background check loop. Manifest handling is in [`manifest`], download and
//! installation in [`install`].

mod install;
mod manifest;

pub(crate) use install::*;
pub(crate) use manifest::*;

use crate::*;

pub(crate) fn release_version() -> &'static str {
    option_env!("SILICIUM_RELEASE_VERSION").unwrap_or(env!("CARGO_PKG_VERSION"))
}

pub(crate) fn release_channel() -> &'static str {
    option_env!("SILICIUM_RELEASE_CHANNEL").unwrap_or(if env!("CARGO_PKG_VERSION").contains('-') {
        "dev"
    } else {
        "prod"
    })
}

pub(crate) fn release_build() -> &'static str {
    option_env!("SILICIUM_RELEASE_BUILD").unwrap_or("")
}

pub(crate) fn update_manifest_url() -> &'static str {
    option_env!("SILICIUM_UPDATE_MANIFEST_URL")
        .unwrap_or("https://vps-910c1dbc.vps.ovh.net/downloads/update-manifest.json")
}

pub(crate) fn default_update_interval() -> u64 {
    if release_channel() == "dev" {
        30
    } else {
        21_600
    }
}

pub(crate) fn default_update_status() -> UpdateStatus {
    UpdateStatus {
        current_version: release_version().to_string(),
        current_channel: release_channel().to_string(),
        current_build: release_build().to_string(),
        latest_version: String::new(),
        latest_build: String::new(),
        latest_content_id: String::new(),
        state: "unknown".to_string(),
        update_available: false,
        automatic: true,
        last_checked_utc: String::new(),
        error: String::new(),
        check_interval_seconds: default_update_interval(),
    }
}

pub(crate) fn update_status_path() -> PathBuf {
    app_state_dir().join("update-status.json")
}

pub(crate) fn update_lock_path() -> PathBuf {
    app_state_dir().join("update-check.lock")
}

pub(crate) fn update_install_lock_path() -> PathBuf {
    app_state_dir().join("update-install.lock")
}

pub(crate) fn update_install_failure_path() -> PathBuf {
    app_state_dir().join("update-install-failure.json")
}

pub(crate) fn update_failure_retry_interval() -> u64 {
    // A failed artifact is blocked until the manifest publishes a different
    // content id. Keep the background loop quiet even on development builds.
    21_600
}

pub(crate) fn read_update_install_failure() -> Option<UpdateInstallFailure> {
    fs::read_to_string(update_install_failure_path())
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
}

pub(crate) fn write_update_install_failure(failure: &UpdateInstallFailure) {
    let path = update_install_failure_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(raw) = serde_json::to_vec_pretty(failure) {
        let _ = fs::write(path, raw);
    }
}

pub(crate) fn clear_update_install_failure() {
    let _ = fs::remove_file(update_install_failure_path());
}

pub(crate) fn update_install_failure_matches(
    failure: &UpdateInstallFailure,
    release: &UpdateRelease,
) -> bool {
    if !failure.content_id.trim().is_empty() && !release.content_id.trim().is_empty() {
        return failure.content_id.trim() == release.content_id.trim();
    }
    failure.version.trim() == release.version.trim() && failure.build.trim() == release.build.trim()
}

pub(crate) fn record_update_install_failure(release: &UpdateRelease, error: &str) {
    write_update_install_failure(&UpdateInstallFailure {
        content_id: release.content_id.clone(),
        version: release.version.clone(),
        build: release.build.clone(),
        error: error.to_string(),
        failed_at_utc: current_utc(),
    });
}

pub(crate) fn read_update_status() -> Option<UpdateStatus> {
    fs::read_to_string(update_status_path())
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
}

pub(crate) fn write_update_status(status: &UpdateStatus) {
    let path = update_status_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(raw) = serde_json::to_vec_pretty(status) {
        let _ = fs::write(path, raw);
    }
}

pub(crate) fn acquire_update_lock() -> bool {
    let path = update_lock_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(metadata) = fs::metadata(&path) {
        let stale = metadata
            .modified()
            .ok()
            .and_then(|time| time.elapsed().ok())
            .map(|age| age > Duration::from_secs(300))
            .unwrap_or(true);
        if stale {
            let _ = fs::remove_file(&path);
        }
    }
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .and_then(|mut file| {
            use std::io::Write;
            writeln!(file, "{}", std::process::id())
        })
        .is_ok()
}

pub(crate) fn release_update_lock() {
    let _ = fs::remove_file(update_lock_path());
}

pub(crate) fn acquire_update_install_lock(content_id: &str) -> Result<bool, String> {
    let path = update_install_lock_path();
    acquire_install_lock_at(&path, content_id, Duration::from_secs(30 * 60))
}

pub(crate) fn acquire_install_lock_at(
    path: &Path,
    content_id: &str,
    stale_after: Duration,
) -> Result<bool, String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    if let Ok(metadata) = fs::metadata(path) {
        let stale = metadata
            .modified()
            .ok()
            .and_then(|time| time.elapsed().ok())
            .map(|age| age > stale_after)
            .unwrap_or(true);
        if stale {
            let _ = fs::remove_file(path);
        }
    }
    match OpenOptions::new().write(true).create_new(true).open(path) {
        Ok(mut file) => {
            use std::io::Write;
            writeln!(file, "{content_id}").map_err(|error| error.to_string())?;
            Ok(true)
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => Ok(false),
        Err(error) => Err(error.to_string()),
    }
}

pub(crate) fn release_update_install_lock() {
    let _ = fs::remove_file(update_install_lock_path());
}

pub(crate) fn check_for_update_once(auto_install: bool) -> UpdateStatus {
    if !acquire_update_lock() {
        return read_update_status().unwrap_or_else(default_update_status);
    }
    let mut status = default_update_status();
    status.state = "checking".to_string();
    write_update_status(&status);
    let result = check_for_update_locked(&mut status, auto_install);
    if let Err(error) = result {
        status.state = "error".to_string();
        status.error = error;
        status.last_checked_utc = current_utc();
        write_update_status(&status);
    }
    release_update_lock();
    status
}

pub(crate) fn check_for_update_locked(
    status: &mut UpdateStatus,
    auto_install: bool,
) -> Result<(), String> {
    let release = fetch_update_release()?;
    status.latest_version = release.version.clone();
    status.latest_build = release.build.clone();
    status.latest_content_id = release.content_id.clone();
    status.check_interval_seconds = if release.check_interval_seconds > 0 {
        release.check_interval_seconds.max(15)
    } else {
        default_update_interval()
    };
    status.automatic = release.auto_install;
    status.last_checked_utc = current_utc();
    status.update_available = release_requires_update(
        &release.version,
        &release.build,
        release_version(),
        release_build(),
    );
    status.error.clear();
    if !status.update_available {
        clear_update_install_failure();
    } else if let Some(failure) = read_update_install_failure() {
        if update_install_failure_matches(&failure, &release) {
            status.state = "error".to_string();
            status.error = format!(
                "update_install_blocked:{}:{}",
                failure.error, failure.content_id
            );
            status.check_interval_seconds = update_failure_retry_interval();
            write_update_status(status);
            return Ok(());
        }
    }
    status.state = if status.update_available {
        "available"
    } else {
        "current"
    }
    .to_string();
    write_update_status(status);

    if auto_install && status.update_available && release.auto_install {
        if node_has_active_work() {
            status.state = "waiting_for_idle".to_string();
            write_update_status(status);
            return Ok(());
        }
        if !acquire_update_install_lock(&release.content_id)? {
            status.state = "installing".to_string();
            write_update_status(status);
            return Ok(());
        }
        status.state = "downloading".to_string();
        write_update_status(status);
        let installer = match download_update(&release) {
            Ok(installer) => installer,
            Err(error) => {
                record_update_install_failure(&release, &error);
                status.check_interval_seconds = update_failure_retry_interval();
                release_update_install_lock();
                return Err(error);
            }
        };
        status.state = "installing".to_string();
        write_update_status(status);
        if let Err(error) = schedule_update_install(&installer, &release) {
            record_update_install_failure(&release, &error);
            status.check_interval_seconds = update_failure_retry_interval();
            release_update_install_lock();
            return Err(error);
        }
    }
    Ok(())
}

pub(crate) fn node_has_active_work() -> bool {
    let Some(root) = discover_managed_runtime_root() else {
        return false;
    };
    let events_path = root
        .join("Network")
        .join(".silicium")
        .join("networked")
        .join("silicium-desktop-node")
        .join("export")
        .join("node.events.ndjson");
    let Ok(raw) = fs::read_to_string(events_path) else {
        return false;
    };
    for line in raw.lines().rev().take(500) {
        let Ok(event) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        match event.get("kind").and_then(Value::as_str).unwrap_or("") {
            "task_started" => return true,
            "task" | "request" | "result_return" => return false,
            _ => {}
        }
    }
    false
}

pub(crate) fn run_background_update_loop() {
    loop {
        let status = check_for_update_once(true);
        thread::sleep(Duration::from_secs(status.check_interval_seconds.max(15)));
    }
}
