//! The Silicium AI runtime ("Catalogue IA"): the Python engine that runs the
//! models of the AI catalogue for the node (`apps/silicium-ai-runtime`), set
//! up and started by this app next to Ollama when the user turns AI tasks on.
//!
//! - **Same switch**: "Tâches IA" (`ai/settings.json`) turns both on or off.
//! - **Pinned**: `uv` comes from its PyPI wheel, whose SHA-256 is compiled in
//!   ([`UV_WHEELS`]); `uv` then installs Python 3.12 and the locked
//!   dependencies of this platform, every package checked by its hash
//!   (`--require-hashes`, wheels only). The runtime's own sources are compiled
//!   into the app: what runs is what was reviewed.
//! - **Private**: it listens on `127.0.0.1:`[`AI_RUNTIME_PORT`] with a token
//!   of its own, works offline and only loads models from the node's
//!   `<data dir>/ai/hf/models` (see the runtime's `sandbox.py`).
//! - **Supervised**: started by the supervisor ([`ensure_ai_runtime`]),
//!   stopped with the node or when AI tasks are turned off
//!   ([`stop_ai_runtime`]). The node always gets `SILICIUM_AI_RUNTIME_URL`:
//!   without the runtime behind it, it simply takes no catalogue task.
//!
//! Progress is written to `ai/runtime-status.json` (installer thread, window
//! and supervisor share it).

use crate::*;

/// Port of the AI runtime (Ollama keeps 11435).
pub(crate) const AI_RUNTIME_PORT: u16 = 11436;
const UV_VERSION: &str = "0.9.5";
const PYTHON_VERSION: &str = "3.12";

/// A `uv` wheel of [`UV_VERSION`] on PyPI for one platform.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct UvWheel {
    pub(crate) os: &'static str,
    pub(crate) arch: &'static str,
    pub(crate) url: &'static str,
    pub(crate) sha256: &'static str,
}

/// From `https://pypi.org/pypi/uv/0.9.5/json`.
pub(crate) const UV_WHEELS: &[UvWheel] = &[
    UvWheel { os: "windows", arch: "x86_64", url: "https://files.pythonhosted.org/packages/af/14/0f07d0b2e561548b4e3006208480a5fce8cdaae5247d85efbfb56e8e596b/uv-0.9.5-py3-none-win_amd64.whl", sha256: "48a12390421f91af8a8993cf15c38297c0bb121936046286e287975b2fbf1789" },
    UvWheel { os: "linux", arch: "x86_64", url: "https://files.pythonhosted.org/packages/9b/83/a0bdf4abf86ede79b427778fe27e2b4a022c98a7a8ea1745dcd6c6561f17/uv-0.9.5-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", sha256: "6507bbbcd788553ec4ad5a96fa19364dc0f58b023e31d79868773559a83ec181" },
    UvWheel { os: "macos", arch: "aarch64", url: "https://files.pythonhosted.org/packages/b2/26/bd6438cf6d84a6b0b608bcbe9f353d8e424f8fe3b1b73a768984a76bf80b/uv-0.9.5-py3-none-macosx_11_0_arm64.whl", sha256: "8603bb902e578463c50c3ddd4ee376ba4172ccdf4979787f8948747d1bb0e18b" },
];

/// Locked dependencies of each platform (`uv pip compile --generate-hashes`).
fn requirements_for(os: &str, arch: &str) -> Option<&'static str> {
    match (os, arch) {
        ("windows", "x86_64") => Some(include_str!(
            "../../../silicium-ai-runtime/requirements/windows-x86_64.txt"
        )),
        ("linux", "x86_64") => Some(include_str!(
            "../../../silicium-ai-runtime/requirements/linux-x86_64.txt"
        )),
        ("macos", "aarch64") => Some(include_str!(
            "../../../silicium-ai-runtime/requirements/macos-aarch64.txt"
        )),
        _ => None,
    }
}

/// Sources of the runtime, compiled into the app.
const RUNTIME_SOURCES: &[(&str, &str)] = &[
    (
        "silicium_ai_runtime/__init__.py",
        include_str!("../../../silicium-ai-runtime/silicium_ai_runtime/__init__.py"),
    ),
    (
        "silicium_ai_runtime/__main__.py",
        include_str!("../../../silicium-ai-runtime/silicium_ai_runtime/__main__.py"),
    ),
    (
        "silicium_ai_runtime/inputs.py",
        include_str!("../../../silicium-ai-runtime/silicium_ai_runtime/inputs.py"),
    ),
    (
        "silicium_ai_runtime/loader.py",
        include_str!("../../../silicium-ai-runtime/silicium_ai_runtime/loader.py"),
    ),
    (
        "silicium_ai_runtime/sandbox.py",
        include_str!("../../../silicium-ai-runtime/silicium_ai_runtime/sandbox.py"),
    ),
    (
        "silicium_ai_runtime/server.py",
        include_str!("../../../silicium-ai-runtime/silicium_ai_runtime/server.py"),
    ),
    (
        "silicium_ai_runtime/tasks.py",
        include_str!("../../../silicium-ai-runtime/silicium_ai_runtime/tasks.py"),
    ),
];

pub(crate) fn uv_wheel_for(os: &str, arch: &str) -> Option<UvWheel> {
    UV_WHEELS
        .iter()
        .copied()
        .find(|wheel| wheel.os == os && wheel.arch == arch)
}

/// True when the runtime can be installed on this machine.
pub(crate) fn ai_runtime_supported() -> bool {
    uv_wheel_for(env::consts::OS, env::consts::ARCH).is_some()
        && requirements_for(env::consts::OS, env::consts::ARCH).is_some()
}

pub(crate) fn ai_runtime_url() -> String {
    format!("http://127.0.0.1:{AI_RUNTIME_PORT}")
}

/// Version of what is installed: the uv, Python and dependency pins and the
/// sources. Anything else is another install directory.
fn install_digest() -> String {
    let mut digest = Sha256::new();
    digest.update(UV_VERSION.as_bytes());
    digest.update(PYTHON_VERSION.as_bytes());
    digest.update(
        requirements_for(env::consts::OS, env::consts::ARCH)
            .unwrap_or("")
            .as_bytes(),
    );
    for (path, source) in RUNTIME_SOURCES {
        digest.update(path.as_bytes());
        digest.update(source.as_bytes());
    }
    format!("{:x}", digest.finalize())[..12].to_string()
}

fn runtime_dir() -> PathBuf {
    ai_dir().join(format!("runtime-{}", install_digest()))
}

fn uv_binary() -> PathBuf {
    let name = if cfg!(target_os = "windows") {
        "uv.exe"
    } else {
        "uv"
    };
    ai_dir().join(format!("uv-{UV_VERSION}")).join(name)
}

fn runtime_python() -> PathBuf {
    let env_dir = runtime_dir().join("env");
    if cfg!(target_os = "windows") {
        env_dir.join("Scripts").join("python.exe")
    } else {
        env_dir.join("bin").join("python")
    }
}

fn installed_marker() -> PathBuf {
    runtime_dir().join(".installed")
}

fn runtime_pid_path() -> PathBuf {
    ai_dir().join("runtime.pid")
}

fn runtime_lock_path() -> PathBuf {
    ai_dir().join("runtime-install.lock")
}

/// Token the node gives the runtime (created once, kept in `ai/`).
pub(crate) fn ai_runtime_token() -> String {
    let path = ai_dir().join("runtime-token");
    if let Ok(token) = fs::read_to_string(&path) {
        let token = token.trim().to_string();
        if token.len() == 64 {
            return token;
        }
    }
    let mut seed = Sha256::new();
    seed.update(std::process::id().to_le_bytes());
    seed.update(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
            .to_le_bytes(),
    );
    seed.update(app_state_dir().to_string_lossy().as_bytes());
    if let Ok(mut random) = fs::File::open("/dev/urandom") {
        let mut bytes = [0_u8; 32];
        if random.read_exact(&mut bytes).is_ok() {
            seed.update(bytes);
        }
    }
    let token = format!("{:x}", seed.finalize());
    if fs::create_dir_all(ai_dir()).is_ok() {
        let _ = fs::write(&path, &token);
    }
    token
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct RuntimeProgress {
    state: String,
    message: String,
}

fn write_runtime_progress(state: &str, message: &str) {
    if fs::create_dir_all(ai_dir()).is_ok() {
        let progress = RuntimeProgress {
            state: state.into(),
            message: message.into(),
        };
        if let Ok(text) = serde_json::to_string(&progress) {
            let _ = fs::write(ai_dir().join("runtime-status.json"), text);
        }
    }
}

fn read_runtime_progress() -> RuntimeProgress {
    fs::read_to_string(ai_dir().join("runtime-status.json"))
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default()
}

/// True when the runtime answers its health check with our token.
pub(crate) fn ai_runtime_responding() -> bool {
    let Ok(address) = format!("127.0.0.1:{AI_RUNTIME_PORT}").parse() else {
        return false;
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(3000)));
    let request = format!(
        "GET /v1/health HTTP/1.0\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n",
        ai_runtime_token()
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = String::new();
    let _ = stream.read_to_string(&mut response);
    response.starts_with("HTTP/1.")
        && response.contains(" 200")
        && response.contains("silicium-ai-runtime/1")
}

/// State of the runtime for the window: `off`, `installing`, `installed`,
/// `running`, `unsupported` or `error`.
pub(crate) fn ai_runtime_state() -> (String, String) {
    if !ai_runtime_supported() {
        return ("unsupported".into(), String::new());
    }
    if !ai_enabled() {
        return ("off".into(), String::new());
    }
    if installed_marker().is_file() {
        let state = if ai_runtime_responding() {
            "running"
        } else {
            "installed"
        };
        return (state.into(), String::new());
    }
    let progress = read_runtime_progress();
    match progress.state.as_str() {
        "error" => ("error".into(), progress.message),
        _ => ("installing".into(), progress.message),
    }
}

fn installer_running() -> bool {
    fs::read_to_string(runtime_lock_path())
        .ok()
        .and_then(|text| text.trim().parse::<u32>().ok())
        .is_some_and(process_is_running)
}

/// Starts the installer in the background unless the runtime is installed
/// or being installed.
pub(crate) fn start_ai_runtime_installer() {
    if !ai_runtime_supported() || installed_marker().is_file() || installer_running() {
        return;
    }
    thread::spawn(|| {
        if fs::create_dir_all(ai_dir()).is_err() {
            return;
        }
        if installer_running() {
            return;
        }
        let _ = fs::write(runtime_lock_path(), std::process::id().to_string());
        let result = install_ai_runtime();
        let _ = fs::remove_file(runtime_lock_path());
        match result {
            Ok(()) => write_runtime_progress("installed", ""),
            Err(error) => {
                let _ = append_app_log(&format!("ai_runtime_install_failed: {error}\n"));
                write_runtime_progress("error", &error);
            }
        }
    });
}

fn install_ai_runtime() -> Result<(), String> {
    let (os, arch) = (env::consts::OS, env::consts::ARCH);
    let wheel = uv_wheel_for(os, arch).ok_or("ai_runtime_unsupported_platform")?;
    let requirements = requirements_for(os, arch).ok_or("ai_runtime_unsupported_platform")?;
    write_runtime_progress("installing", "uv");
    install_uv(wheel)?;

    let dir = runtime_dir();
    let staging = dir.with_extension("partial");
    let _ = fs::remove_dir_all(&staging);
    for (path, source) in RUNTIME_SOURCES {
        let target = staging.join("src").join(path);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        fs::write(&target, source).map_err(|error| error.to_string())?;
    }
    let requirements_path = staging.join("requirements.txt");
    fs::write(&requirements_path, requirements).map_err(|error| error.to_string())?;
    let _ = fs::remove_dir_all(&dir);
    fs::rename(&staging, &dir).map_err(|error| error.to_string())?;

    write_runtime_progress("installing", "python");
    run_uv(&["venv", "--python", PYTHON_VERSION, "env"], &dir)?;
    write_runtime_progress("installing", "packages");
    let python = runtime_python();
    run_uv(
        &[
            "pip",
            "install",
            "--python",
            &python.to_string_lossy(),
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--no-deps",
            "-r",
            &dir.join("requirements.txt").to_string_lossy(),
        ],
        &dir,
    )?;
    fs::write(installed_marker(), install_digest()).map_err(|error| error.to_string())?;
    remove_older_runtimes();
    Ok(())
}

/// Downloads the pinned `uv` wheel, checks it and takes `uv` out of it.
fn install_uv(wheel: UvWheel) -> Result<(), String> {
    if uv_binary().is_file() {
        return Ok(());
    }
    let dir = ai_dir();
    let archive = dir.join(format!("uv-{UV_VERSION}.whl"));
    if sha256_file(&archive).ok().as_deref() != Some(wheel.sha256) {
        let partial = archive.with_extension("whl.partial");
        let _ = fs::remove_file(&partial);
        curl_download(wheel.url, &partial, 1800)?;
        let sha256 = sha256_file(&partial)?;
        if sha256 != wheel.sha256 {
            let _ = fs::remove_file(&partial);
            return Err(format!("uv_wheel_hash_mismatch: {sha256}"));
        }
        fs::rename(&partial, &archive).map_err(|error| error.to_string())?;
    }
    let staging = dir.join(format!("uv-{UV_VERSION}.partial"));
    let _ = fs::remove_dir_all(&staging);
    fs::create_dir_all(&staging).map_err(|error| error.to_string())?;
    unzip(&archive, &staging)?;
    let name = if cfg!(target_os = "windows") {
        "uv.exe"
    } else {
        "uv"
    };
    let unpacked = staging
        .join(format!("uv-{UV_VERSION}.data"))
        .join("scripts")
        .join(name);
    if !unpacked.is_file() {
        return Err("uv_binary_missing_in_wheel".into());
    }
    let target = uv_binary();
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::rename(&unpacked, &target).map_err(|error| error.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&target, fs::Permissions::from_mode(0o755));
    }
    let _ = fs::remove_dir_all(&staging);
    let _ = fs::remove_file(&archive);
    Ok(())
}

/// Unpacks a zip archive: `tar` reads zip on Windows 10+ and macOS (bsdtar);
/// on Linux, `unzip` or Python's `zipfile`.
fn unzip(archive: &Path, target: &Path) -> Result<(), String> {
    let attempts: Vec<Vec<String>> = if cfg!(target_os = "linux") {
        vec![
            vec![
                "unzip".into(),
                "-q".into(),
                archive.to_string_lossy().into(),
                "-d".into(),
                target.to_string_lossy().into(),
            ],
            vec![
                "python3".into(),
                "-m".into(),
                "zipfile".into(),
                "-e".into(),
                archive.to_string_lossy().into(),
                target.to_string_lossy().into(),
            ],
            vec![
                "bsdtar".into(),
                "-xf".into(),
                archive.to_string_lossy().into(),
                "-C".into(),
                target.to_string_lossy().into(),
            ],
        ]
    } else {
        let tar = if cfg!(target_os = "windows") {
            "tar.exe"
        } else {
            "tar"
        };
        vec![vec![
            tar.into(),
            "-xf".into(),
            archive.to_string_lossy().into(),
            "-C".into(),
            target.to_string_lossy().into(),
        ]]
    };
    let mut last_error = String::from("no_unzip_tool");
    for attempt in attempts {
        let mut command = Command::new(&attempt[0]);
        command
            .args(&attempt[1..])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::piped());
        configure_detached_process(&mut command);
        match command.output() {
            Ok(output) if output.status.success() => return Ok(()),
            Ok(output) => last_error = String::from_utf8_lossy(&output.stderr).trim().to_string(),
            Err(error) => last_error = error.to_string(),
        }
    }
    Err(format!("uv_unpack_failed:{last_error}"))
}

fn run_uv(arguments: &[&str], dir: &Path) -> Result<(), String> {
    let mut command = Command::new(uv_binary());
    command
        .args(arguments)
        .current_dir(dir)
        .env("UV_PYTHON_INSTALL_DIR", ai_dir().join("python"))
        .env("UV_CACHE_DIR", ai_dir().join("uv-cache"))
        .env("UV_NO_CONFIG", "1")
        .env("UV_PYTHON_PREFERENCE", "only-managed")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    configure_detached_process(&mut command);
    let output = command
        .output()
        .map_err(|error| format!("uv_start_failed:{error}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let tail: String = stderr
            .trim()
            .chars()
            .rev()
            .take(400)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect();
        return Err(format!("uv_{}_failed:{tail}", arguments[0]));
    }
    Ok(())
}

fn remove_older_runtimes() {
    let current = runtime_dir();
    let Ok(entries) = fs::read_dir(ai_dir()) else {
        return;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with("runtime-") && entry.path() != current && entry.path().is_dir() {
            let _ = fs::remove_dir_all(entry.path());
        }
    }
}

/// Starts the runtime when AI tasks are on and it is installed but not
/// running; stops it when they are off. Called by the supervisor loop.
pub(crate) fn ensure_ai_runtime(repo_root: &Path) {
    if !ai_enabled() || !ai_runtime_supported() {
        stop_ai_runtime();
        return;
    }
    if ai_runtime_responding() || runtime_pid().is_some_and(process_is_running) {
        return;
    }
    if !installed_marker().is_file() {
        // Turned on, but the install was interrupted: resume it, unless it
        // failed (the user turns AI tasks off and on to retry).
        if read_runtime_progress().state != "error" {
            start_ai_runtime_installer();
        }
        return;
    }
    let models_root = node_models_root(repo_root);
    let _ = fs::create_dir_all(&models_root);
    let mut command = Command::new(runtime_python());
    command
        .arg("-m")
        .arg("silicium_ai_runtime")
        .arg("--models-root")
        .arg(&models_root)
        .arg("--port")
        .arg(AI_RUNTIME_PORT.to_string())
        .current_dir(runtime_dir())
        .env("PYTHONPATH", runtime_dir().join("src"))
        .env("PYTHONNOUSERSITE", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("SILICIUM_AI_RUNTIME_TOKEN", ai_runtime_token());
    match spawn_detached_with_log(
        command,
        repo_root,
        "silicium-ai-runtime.out.log",
        "silicium-ai-runtime.err.log",
    ) {
        Ok(child) => {
            let _ = fs::write(runtime_pid_path(), child.id().to_string());
            let _ = append_supervisor_log(
                repo_root,
                &format!("ai_runtime_started pid={}\n", child.id()),
            );
        }
        Err(error) => {
            let _ =
                append_supervisor_log(repo_root, &format!("ai_runtime_start_failed: {error}\n"));
        }
    }
}

/// Where the node keeps the models of the catalogue (`workload/hf/runtime.rs`).
fn node_models_root(repo_root: &Path) -> PathBuf {
    runtime_state_dir(repo_root)
        .join("ai")
        .join("hf")
        .join("models")
}

fn runtime_pid() -> Option<u32> {
    fs::read_to_string(runtime_pid_path())
        .ok()?
        .trim()
        .parse()
        .ok()
}

/// Stops the runtime, if it runs.
pub(crate) fn stop_ai_runtime() {
    if let Some(pid) = runtime_pid() {
        if process_is_running(pid) {
            let _ = kill_process_tree(pid);
        }
        let _ = fs::remove_file(runtime_pid_path());
    }
}
