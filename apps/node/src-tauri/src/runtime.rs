//! Location and preparation of the node runtime: repository root resolution,
//! managed runtime copy, packaged runtime discovery, and the raytracer
//! environment given to child processes.

use crate::*;
#[cfg(unix)]
use std::sync::atomic::{AtomicU64, Ordering as AtomicOrdering};

#[cfg(unix)]
static RUNTIME_COPY_SEQUENCE: AtomicU64 = AtomicU64::new(0);

pub(crate) fn resolve_optional_repo_root(_repo_root: Option<&str>) -> Option<PathBuf> {
    if let Some(root) = discover_managed_runtime_root() {
        return Some(root);
    }
    ensure_packaged_runtime_preferred()
}

pub(crate) fn resolve_repo_root(_repo_root: &str) -> Result<PathBuf, String> {
    if let Some(root) = discover_managed_runtime_root() {
        return refresh_managed_runtime_if_needed(root);
    }
    if find_packaged_runtime_root().is_some() {
        return ensure_managed_runtime();
    }
    Err("managed_runtime_not_found".to_string())
}

pub(crate) fn resolve_repo_root_readonly(_repo_root: &str) -> Result<PathBuf, String> {
    if let Some(root) = discover_managed_runtime_root() {
        validate_repo_root(&root)?;
        return Ok(root);
    }
    if find_packaged_runtime_root().is_some() {
        return ensure_managed_runtime();
    }
    Err("managed_runtime_not_found".to_string())
}

pub(crate) fn ensure_packaged_runtime_preferred() -> Option<PathBuf> {
    if find_packaged_runtime_root().is_some() {
        ensure_managed_runtime().ok()
    } else {
        None
    }
}

pub(crate) fn validate_repo_root(repo_root: &Path) -> Result<(), String> {
    if !repo_root.exists() {
        return Err("repo_root_not_found".to_string());
    }
    if !repo_root.join("Network").is_dir() {
        return Err("network_directory_not_found".to_string());
    }
    let suffix = if cfg!(target_os = "windows") { ".exe" } else { "" };
    for binary in ["p2p_node", "compute_daemon"] {
        let path = repo_root
            .join("Network")
            .join("bin")
            .join(format!("{binary}{suffix}"));
        if !path.is_file() {
            return Err("network_runtime_not_found".to_string());
        }
    }
    Ok(())
}

pub(crate) fn managed_runtime_root() -> PathBuf {
    app_state_dir().join("runtime")
}

pub(crate) fn discover_managed_runtime_root() -> Option<PathBuf> {
    let root = managed_runtime_root();
    if validate_repo_root(&root).is_ok() {
        Some(root)
    } else {
        None
    }
}

pub(crate) fn ensure_managed_runtime() -> Result<PathBuf, String> {
    let root = managed_runtime_root();
    let source = find_packaged_runtime_root().ok_or_else(|| {
        format!(
            "managed_runtime_missing: no bundled runtime found. Expected an installed runtime with Network/ under {}",
            root.display()
        )
    })?;
    if same_path(&source, &root) {
        remove_legacy_runtime_assets(&root)?;
        validate_repo_root(&root)?;
        return Ok(root);
    }

    copy_dir_all(&source, &root)?;
    remove_legacy_runtime_assets(&root)?;
    validate_repo_root(&root)?;
    Ok(root)
}

/// Files of earlier bundles that the current runtime no longer ships, relative
/// to the managed runtime root: the Python network runtime (interpreter and
/// site-packages in `tools/`, `Network/tools`, `Network/networked`,
/// `Network/workloads`, the `Network/silicium` CLI and its
/// `deploy/linux/start-node.sh` launcher) and the OpenSSL CLI of releases
/// before dev.14.
pub(crate) const LEGACY_RUNTIME_PATHS: [&str; 6] = [
    "tools",
    "Network/tools",
    "Network/networked",
    "Network/workloads",
    "Network/silicium",
    "deploy",
];

/// Removes the files of earlier bundles from the managed runtime. NSIS
/// upgrades and the managed-runtime copy are additive, so files that disappear
/// from a newer bundle otherwise survive forever. Node data (`.silicium/`) and
/// the binaries in `Network/bin/` are never touched.
pub(crate) fn remove_legacy_runtime_assets(root: &Path) -> Result<(), String> {
    for relative in LEGACY_RUNTIME_PATHS {
        let path = relative
            .split('/')
            .fold(root.to_path_buf(), |path, part| path.join(part));
        let removed = if path.is_dir() {
            fs::remove_dir_all(&path)
        } else if path.exists() {
            fs::remove_file(&path)
        } else {
            continue;
        };
        removed
            .map_err(|error| format!("legacy_runtime_cleanup_failed:{}:{error}", path.display()))?;
    }
    Ok(())
}

pub(crate) fn refresh_managed_runtime_if_needed(root: PathBuf) -> Result<PathBuf, String> {
    if !same_path(&root, &managed_runtime_root()) {
        return Ok(root);
    }
    ensure_managed_runtime()
}

pub(crate) fn find_packaged_runtime_root() -> Option<PathBuf> {
    let exe = env::current_exe().ok();
    let app_dir = env::var_os("APPDIR")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from);
    let mut candidates = exe
        .as_deref()
        .map(|path| packaged_runtime_candidates(path, app_dir.as_deref()))
        .unwrap_or_default();
    candidates.push(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("resources")
            .join("runtime"),
    );

    candidates
        .into_iter()
        .find(|path| validate_repo_root(path).is_ok())
}

pub(crate) fn packaged_runtime_candidates(exe: &Path, app_dir: Option<&Path>) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    let executable_name = exe.file_stem().filter(|name| !name.is_empty());

    if cfg!(target_os = "linux") {
        // Tauri's Linux resource directory is /usr/lib/<binary>/ for both
        // AppImage and .deb bundles. AppImage exposes the mounted root as
        // APPDIR; keep both forms because current_exe() can be resolved from
        // a wrapper or from an extracted AppImage.
        if let Some(app_dir) = app_dir {
            candidates.extend(linux_resource_runtime_candidates(
                &app_dir.join("usr").join("lib"),
                executable_name,
            ));
        }

        // linuxdeploy's AppRun.wrapped can be reported as current_exe()
        // without exporting APPDIR. Walk its ancestors so a supervisor
        // started by XDG autostart can still find the mounted AppImage
        // resources instead of falling back to a stale managed runtime.
        let mut ancestor = exe.parent();
        while let Some(path) = ancestor {
            candidates.push(
                path.join("usr")
                    .join("lib")
                    .join("Silicium Node")
                    .join("resources")
                    .join("runtime"),
            );
            ancestor = path.parent();
        }
    }

    if let Some(parent) = exe.parent() {
        candidates.push(parent.join("runtime"));
        candidates.push(parent.join("resources").join("runtime"));

        if cfg!(target_os = "linux") {
            // Installed .deb/.rpm: /usr/bin/<binary> -> /usr/lib/<product>
            // name/resources/runtime. Tauri uses productName for the resource
            // directory, so it may contain spaces and differ from the binary
            // name (for example, "Silicium Node" vs "silicium-node").
            candidates.extend(linux_resource_runtime_candidates(
                &parent.join("..").join("lib"),
                executable_name,
            ));
        }

        // Keep the Windows and macOS layouts used by the existing desktop
        // build, as well as Tauri's macOS-style fallback.
        candidates.push(parent.join("..").join("Resources").join("runtime"));
    }

    candidates
}

pub(crate) fn linux_resource_runtime_candidates(
    lib_dir: &Path,
    executable_name: Option<&OsStr>,
) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(name) = executable_name {
        candidates.push(
            lib_dir
                .join(Path::new(name))
                .join("resources")
                .join("runtime"),
        );
    }
    let Ok(entries) = fs::read_dir(lib_dir) else {
        return candidates;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            candidates.push(path.join("resources").join("runtime"));
        }
    }
    candidates
}

pub(crate) fn same_path(left: &Path, right: &Path) -> bool {
    match (left.canonicalize(), right.canonicalize()) {
        (Ok(left), Ok(right)) => left == right,
        _ => left == right,
    }
}

pub(crate) fn copy_dir_all(source: &Path, target: &Path) -> Result<(), String> {
    fs::create_dir_all(target).map_err(|error| error.to_string())?;
    for entry in fs::read_dir(source).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let source_path = entry.path();
        let target_path = target.join(entry.file_name());
        if source_path.is_dir() && source_path.ends_with(Path::new("tools").join("openssl")) {
            // Old NSIS upgrades can retain this directory in the packaged
            // resources. Never copy it back into the managed runtime, even
            // when two runtime refreshes overlap.
            continue;
        }
        if source_path.is_dir() {
            copy_dir_all(&source_path, &target_path)?;
        } else {
            if let Some(parent) = target_path.parent() {
                fs::create_dir_all(parent).map_err(|error| error.to_string())?;
            }
            copy_runtime_file(&source_path, &target_path)?;
        }
    }
    Ok(())
}

/// Replaces runtime files by rename on Unix. `fs::copy` truncates its target,
/// which returns ETXTBSY when a managed executable is currently running.
/// Copying beside the target and renaming keeps the old inode available to
/// running workers while new processes see the complete replacement.
fn copy_runtime_file(source: &Path, target: &Path) -> Result<(), String> {
    #[cfg(unix)]
    {
        let parent = target
            .parent()
            .ok_or_else(|| format!("runtime_target_has_no_parent:{}", target.display()))?;
        let temporary = loop {
            let sequence = RUNTIME_COPY_SEQUENCE.fetch_add(1, AtomicOrdering::Relaxed);
            let candidate = parent.join(format!(
                ".silicium-runtime-copy-{}-{sequence}",
                std::process::id()
            ));
            match OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&candidate)
            {
                Ok(file) => {
                    drop(file);
                    break candidate;
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error.to_string()),
            }
        };

        if let Err(error) = fs::copy(source, &temporary) {
            let _ = fs::remove_file(&temporary);
            return Err(error.to_string());
        }
        if let Err(error) = fs::rename(&temporary, target) {
            let _ = fs::remove_file(&temporary);
            return Err(error.to_string());
        }
        Ok(())
    }
    #[cfg(not(unix))]
    {
        fs::copy(source, target)
            .map(|_| ())
            .map_err(|error| error.to_string())
    }
}

pub(crate) fn apply_raytracer_env(command: &mut Command, repo_root: &Path) {
    let env_file = repo_root
        .join(".silicium")
        .join("env")
        .join("raytracer.env");
    let Ok(content) = fs::read_to_string(env_file) else {
        return;
    };
    for line in content.lines() {
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        if key == "SILICIUM_RAYTRACER_BIN" || key == "SILICIUM_RAYTRACER_ASSETS_DIR" {
            let resolved = resolve_runtime_env_path(repo_root, value);
            command.env(key, resolved);
        }
    }
}

pub(crate) fn resolve_runtime_env_path(repo_root: &Path, value: &str) -> PathBuf {
    let path = PathBuf::from(value.trim());
    if path.is_absolute() {
        path
    } else {
        repo_root.join(path)
    }
}
