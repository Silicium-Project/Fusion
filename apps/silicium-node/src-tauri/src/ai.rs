//! AI tasks ("Traitement par IA"): the Ollama runtime this app downloads
//! and runs for the node, when the user turns AI tasks on.
//!
//! - **Opt-in**: off by default (`ai/settings.json`); turning it on
//!   downloads the pinned Ollama release (about 1.4 GB on Windows and Linux,
//!   GPU libraries included) and later the model (1.1 GB, by the node).
//! - **Pinned**: one Ollama version, the SHA-256 of each archive compiled in
//!   ([`OLLAMA_ASSETS`]); a download that does not match is deleted.
//! - **Private**: Ollama listens on `127.0.0.1:`[`OLLAMA_PORT`] only, keeps
//!   its models under `ai/models`, and never touches an Ollama the user may
//!   have installed (port 11434, `~/.ollama`).
//! - **Supervised**: the supervisor starts it next to the node
//!   ([`ensure_ollama`]) and stops it when AI tasks are turned off or the
//!   node is stopped ([`stop_ollama`]). The node always gets
//!   `SILICIUM_OLLAMA_URL`: without Ollama behind it, it simply takes no AI
//!   task.
//!
//! The installer runs in a thread of the app; its progress is written to
//! `ai/status.json` so the supervisor and the window share it.

use crate::*;

/// Ollama release run by this app.
pub(crate) const OLLAMA_VERSION: &str = "0.40.4";
/// Port of the app's Ollama (the user's own Ollama keeps 11434).
pub(crate) const OLLAMA_PORT: u16 = 11435;
/// Name prefix of the model the node imports (`silicium-llm`).
const MODEL_PREFIX: &str = "silicium-qwen2.5-1.5b-instruct-";

/// An Ollama release archive for one platform.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct OllamaAsset {
    pub(crate) os: &'static str,
    pub(crate) arch: &'static str,
    pub(crate) name: &'static str,
    pub(crate) sha256: &'static str,
}

/// Archives of [`OLLAMA_VERSION`] (`sha256sum.txt` of the GitHub release).
pub(crate) const OLLAMA_ASSETS: &[OllamaAsset] = &[
    OllamaAsset { os: "windows", arch: "x86_64", name: "ollama-windows-amd64.zip", sha256: "7485a1172f8527db4342a63521b9342fc466185ff0855da378cc864ecf6354cf" },
    OllamaAsset { os: "windows", arch: "aarch64", name: "ollama-windows-arm64.zip", sha256: "1fe50fb62ddcfc5fe102322e4a35043ccbf4e821adfa4ef41eee21af0aa158a7" },
    OllamaAsset { os: "linux", arch: "x86_64", name: "ollama-linux-amd64.tar.zst", sha256: "15f31e9576d15a481e099b4145dba6e9f8c1f295927d6b8895300ae30ed3740a" },
    OllamaAsset { os: "linux", arch: "aarch64", name: "ollama-linux-arm64.tar.zst", sha256: "1a314ac530d2c23bf6d2aaaf4a4aba8cc0b2a4ee8bc8fae3f3aa88bff7f7177b" },
    OllamaAsset { os: "macos", arch: "x86_64", name: "ollama-darwin.tgz", sha256: "a4ceae4b2aaf18df37ebcbfb56ba3a37a87838631112d66c2be07268693c8d58" },
    OllamaAsset { os: "macos", arch: "aarch64", name: "ollama-darwin.tgz", sha256: "a4ceae4b2aaf18df37ebcbfb56ba3a37a87838631112d66c2be07268693c8d58" },
];

/// The archive for this machine, if Ollama ships one.
pub(crate) fn ollama_asset() -> Option<OllamaAsset> {
    asset_for(env::consts::OS, env::consts::ARCH)
}

pub(crate) fn asset_for(os: &str, arch: &str) -> Option<OllamaAsset> {
    OLLAMA_ASSETS
        .iter()
        .copied()
        .find(|asset| asset.os == os && asset.arch == arch)
}

pub(crate) fn ollama_url() -> String {
    format!("http://127.0.0.1:{OLLAMA_PORT}")
}

pub(crate) fn ai_dir() -> PathBuf {
    app_state_dir().join("ai")
}

fn install_dir() -> PathBuf {
    ai_dir().join(format!("ollama-{OLLAMA_VERSION}"))
}

fn models_dir() -> PathBuf {
    ai_dir().join("models")
}

fn ollama_pid_path() -> PathBuf {
    ai_dir().join("ollama.pid")
}

/// What the window shows about AI tasks.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub(crate) struct AiStatus {
    pub(crate) enabled: bool,
    /// `off`, `downloading`, `installing`, `installed`, `running`,
    /// `unsupported` or `error`.
    pub(crate) state: String,
    pub(crate) message: String,
    pub(crate) downloaded_bytes: u64,
    pub(crate) version: String,
    /// The node has imported the model into Ollama.
    pub(crate) model_ready: bool,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct AiSettings {
    enabled: bool,
}

/// Progress of the installer, shared through `ai/status.json`.
#[derive(Debug, Default, Serialize, Deserialize)]
struct InstallProgress {
    state: String,
    message: String,
    updated_unix: u64,
}

pub(crate) fn ai_enabled() -> bool {
    fs::read_to_string(ai_dir().join("settings.json"))
        .ok()
        .and_then(|text| serde_json::from_str::<AiSettings>(&text).ok())
        .is_some_and(|settings| settings.enabled)
}

fn write_settings(enabled: bool) -> Result<(), String> {
    fs::create_dir_all(ai_dir()).map_err(|error| error.to_string())?;
    let text = serde_json::to_string(&AiSettings { enabled }).map_err(|error| error.to_string())?;
    fs::write(ai_dir().join("settings.json"), text).map_err(|error| error.to_string())
}

fn write_progress(state: &str, message: &str) {
    let progress = InstallProgress {
        state: state.to_string(),
        message: message.to_string(),
        updated_unix: SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs(),
    };
    if fs::create_dir_all(ai_dir()).is_ok() {
        if let Ok(text) = serde_json::to_string(&progress) {
            let _ = fs::write(ai_dir().join("status.json"), text);
        }
    }
}

fn read_progress() -> InstallProgress {
    fs::read_to_string(ai_dir().join("status.json"))
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default()
}

/// The Ollama executable of the installed release, if any.
pub(crate) fn ollama_binary() -> Option<PathBuf> {
    let name = if cfg!(target_os = "windows") { "ollama.exe" } else { "ollama" };
    let root = install_dir();
    [root.join(name), root.join("bin").join(name)]
        .into_iter()
        .find(|path| path.is_file())
}

/// True when the app's Ollama answers on its port.
pub(crate) fn ollama_responding() -> bool {
    let Ok(address) = format!("127.0.0.1:{OLLAMA_PORT}").parse() else {
        return false;
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(1500)));
    if stream
        .write_all(b"GET /api/version HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut response = String::new();
    let _ = stream.read_to_string(&mut response);
    response.starts_with("HTTP/1.") && response.contains(" 200") && response.contains("\"version\"")
}

fn model_ready() -> bool {
    curl_get(&format!("{}/api/tags", ollama_url()), 3)
        .map(|body| body.contains(MODEL_PREFIX))
        .unwrap_or(false)
}

/// The state of AI tasks on this PC.
pub(crate) fn ai_status() -> AiStatus {
    let enabled = ai_enabled();
    let progress = read_progress();
    let mut status = AiStatus {
        enabled,
        state: "off".into(),
        message: String::new(),
        downloaded_bytes: 0,
        version: OLLAMA_VERSION.into(),
        model_ready: false,
    };
    if ollama_asset().is_none() {
        status.state = "unsupported".into();
        status.message = format!("Ollama n'est pas disponible pour {} {}", env::consts::OS, env::consts::ARCH);
        return status;
    }
    if !enabled {
        return status;
    }
    if ollama_binary().is_some() {
        if ollama_responding() {
            status.state = "running".into();
            status.model_ready = model_ready();
        } else {
            status.state = "installed".into();
        }
        return status;
    }
    status.state = match progress.state.as_str() {
        "downloading" | "installing" | "error" => progress.state.clone(),
        _ => "installing".into(),
    };
    status.message = progress.message;
    if let Some(asset) = ollama_asset() {
        status.downloaded_bytes = fs::metadata(ai_dir().join(format!("{}.partial", asset.name)))
            .map(|meta| meta.len())
            .unwrap_or(0);
    }
    status
}

/// Turns AI tasks on (installing Ollama in the background) or off
/// (stopping it; the files are kept for a later turn-on).
pub(crate) fn set_ai_enabled(enabled: bool) -> Result<AiStatus, String> {
    if enabled && ollama_asset().is_none() {
        return Err("ai_unsupported_platform".into());
    }
    write_settings(enabled)?;
    if enabled {
        start_installer();
    } else {
        stop_ollama();
        write_progress("off", "");
    }
    Ok(ai_status())
}

/// Downloads, checks and unpacks the pinned Ollama release.
fn install_ollama() -> Result<(), String> {
    let asset = ollama_asset().ok_or("ai_unsupported_platform")?;
    let dir = ai_dir();
    fs::create_dir_all(&dir).map_err(|error| error.to_string())?;
    // One installer at a time (the window and the supervisor may both try);
    // the lock names the installing process, so a crash does not block.
    if installer_running() {
        return Ok(());
    }
    let lock = install_lock_path();
    fs::write(&lock, std::process::id().to_string()).map_err(|error| error.to_string())?;
    let result = download_and_unpack(asset, &dir);
    let _ = fs::remove_file(&lock);
    result
}

fn install_lock_path() -> PathBuf {
    ai_dir().join("install.lock")
}

/// True while a process of this app is installing Ollama.
fn installer_running() -> bool {
    fs::read_to_string(install_lock_path())
        .ok()
        .and_then(|text| text.trim().parse::<u32>().ok())
        .is_some_and(process_is_running)
}

/// Starts the installer in the background unless Ollama is installed or
/// being installed.
fn start_installer() {
    if ollama_binary().is_some() || installer_running() {
        return;
    }
    thread::spawn(|| {
        if let Err(error) = install_ollama() {
            let _ = append_app_log(&format!("ollama_install_failed: {error}\n"));
            write_progress("error", &error);
        }
    });
}

fn download_and_unpack(asset: OllamaAsset, dir: &Path) -> Result<(), String> {
    let archive = dir.join(asset.name);
    if sha256_file(&archive).ok().as_deref() != Some(asset.sha256) {
        let partial = dir.join(format!("{}.partial", asset.name));
        let _ = fs::remove_file(&partial);
        write_progress("downloading", "");
        let url = format!(
            "https://github.com/ollama/ollama/releases/download/v{OLLAMA_VERSION}/{}",
            asset.name
        );
        curl_download(&url, &partial, 3 * 3600)?;
        let sha256 = sha256_file(&partial)?;
        if sha256 != asset.sha256 {
            let _ = fs::remove_file(&partial);
            return Err(format!("ollama_archive_hash_mismatch: {sha256}"));
        }
        fs::rename(&partial, &archive).map_err(|error| error.to_string())?;
    }
    write_progress("installing", "");
    let staging = dir.join(format!("ollama-{OLLAMA_VERSION}.partial"));
    let _ = fs::remove_dir_all(&staging);
    fs::create_dir_all(&staging).map_err(|error| error.to_string())?;
    unpack(&archive, &staging)?;
    let target = install_dir();
    let _ = fs::remove_dir_all(&target);
    fs::rename(&staging, &target).map_err(|error| error.to_string())?;
    if ollama_binary().is_none() {
        return Err("ollama_binary_missing_after_unpack".into());
    }
    #[cfg(unix)]
    if let Some(binary) = ollama_binary() {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&binary, fs::Permissions::from_mode(0o755));
    }
    let _ = fs::remove_file(&archive);
    remove_older_releases(dir);
    write_progress("installed", "");
    Ok(())
}

/// Unpacks with the system `tar` (bsdtar on Windows 10+ and macOS reads
/// zip archives; GNU tar on Linux needs zstd for `.tar.zst`).
fn unpack(archive: &Path, target: &Path) -> Result<(), String> {
    let name = archive.to_string_lossy().to_string();
    let mut command = Command::new(if cfg!(target_os = "windows") { "tar.exe" } else { "tar" });
    if name.ends_with(".tar.zst") {
        command.arg("--zstd").arg("-xf");
    } else if name.ends_with(".tgz") {
        command.arg("-xzf");
    } else {
        command.arg("-xf");
    }
    command
        .arg(archive)
        .arg("-C")
        .arg(target)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    configure_detached_process(&mut command);
    let output = command.output().map_err(|error| format!("tar_start_failed:{error}"))?;
    if !output.status.success() {
        return Err(format!(
            "ollama_unpack_failed:{}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(())
}

fn remove_older_releases(dir: &Path) {
    let current = format!("ollama-{OLLAMA_VERSION}");
    let Ok(entries) = fs::read_dir(dir) else { return };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with("ollama-") && name != current && entry.path().is_dir() {
            let _ = fs::remove_dir_all(entry.path());
        }
    }
}

/// Starts the app's Ollama when AI tasks are on and it is installed but not
/// running; stops it when they are off. Called by the supervisor loop.
pub(crate) fn ensure_ollama(repo_root: &Path) {
    if !ai_enabled() {
        stop_ollama();
        return;
    }
    if ollama_responding() || ollama_pid().is_some_and(process_is_running) {
        return;
    }
    let Some(binary) = ollama_binary() else {
        // Turned on, but the install was interrupted (app closed, crash):
        // the supervisor resumes it, unless it failed (the user retries).
        if read_progress().state != "error" {
            start_installer();
        }
        return;
    };
    let _ = fs::create_dir_all(models_dir());
    let mut command = Command::new(binary);
    command
        .arg("serve")
        .current_dir(ai_dir())
        .env("OLLAMA_HOST", format!("127.0.0.1:{OLLAMA_PORT}"))
        .env("OLLAMA_MODELS", models_dir())
        .env("OLLAMA_KEEP_ALIVE", "10m")
        .env("OLLAMA_NUM_PARALLEL", "1")
        .env("OLLAMA_MAX_LOADED_MODELS", "1");
    match spawn_detached_with_log(command, repo_root, "silicium-ollama.out.log", "silicium-ollama.err.log") {
        Ok(child) => {
            let _ = fs::write(ollama_pid_path(), child.id().to_string());
            let _ = append_supervisor_log(repo_root, &format!("ollama_started pid={}\n", child.id()));
        }
        Err(error) => {
            let _ = append_supervisor_log(repo_root, &format!("ollama_start_failed: {error}\n"));
        }
    }
}

fn ollama_pid() -> Option<u32> {
    fs::read_to_string(ollama_pid_path()).ok()?.trim().parse().ok()
}

/// Stops the app's Ollama, if it runs.
pub(crate) fn stop_ollama() {
    if let Some(pid) = ollama_pid() {
        if process_is_running(pid) {
            let _ = kill_process_tree(pid);
        }
        let _ = fs::remove_file(ollama_pid_path());
    }
}
