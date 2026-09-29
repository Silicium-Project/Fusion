//! Location and preparation of the node runtime: repository root resolution,
//! managed runtime copy, packaged runtime discovery, and the PATH / raytracer
//! environment given to child processes.

use crate::*;

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
    if !repo_root.join("Network").join("silicium").is_file() {
        return Err("network_runtime_not_found".to_string());
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

pub(crate) fn remove_legacy_runtime_assets(root: &Path) -> Result<(), String> {
    // Releases before dev.14 bundled the OpenSSL CLI and added it to PATH.
    // NSIS upgrades and the managed-runtime copy are additive, so files that
    // disappear from a newer bundle otherwise survive forever. Cryptography
    // uses its own Python extension and does not need this executable.
    let legacy_openssl = root.join("tools").join("openssl");
    if legacy_openssl.exists() {
        fs::remove_dir_all(&legacy_openssl).map_err(|error| {
            format!(
                "legacy_runtime_cleanup_failed:{}:{error}",
                legacy_openssl.display()
            )
        })?;
    }
    // The integrated Python daemon only needs networked_runtime.py. Older
    // bundles copied the complete Rust workspaces, including Cargo targets,
    // into the user profile. Besides wasting disk, that allowed the CLI to
    // compile an experimental node during activation.
    let legacy_networked_crates = root.join("Network").join("networked");
    for crate_name in [
        "compute_daemon",
        "p2p_node",
        "reputation_bridge",
        "silicium_node_core",
    ] {
        let path = legacy_networked_crates.join(crate_name);
        if path.exists() {
            fs::remove_dir_all(&path).map_err(|error| {
                format!("legacy_runtime_cleanup_failed:{}:{error}", path.display())
            })?;
        }
    }
    let legacy_raytracer_target = root
        .join("Network")
        .join("workloads")
        .join("raytracer")
        .join("native")
        .join("target");
    if legacy_raytracer_target.exists() {
        fs::remove_dir_all(&legacy_raytracer_target).map_err(|error| {
            format!(
                "legacy_runtime_cleanup_failed:{}:{error}",
                legacy_raytracer_target.display()
            )
        })?;
    }
    Ok(())
}

pub(crate) fn refresh_managed_runtime_if_needed(root: PathBuf) -> Result<PathBuf, String> {
    if !same_path(&root, &managed_runtime_root()) {
        return Ok(root);
    }
    ensure_managed_runtime()
}

pub(crate) fn is_managed_runtime_root(root: &Path) -> bool {
    same_path(root, &managed_runtime_root())
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
            fs::copy(&source_path, &target_path).map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

pub(crate) fn apply_runtime_path(command: &mut Command, repo_root: &Path) {
    let mut path_entries = Vec::new();
    if is_managed_runtime_root(repo_root) {
        command.env("SILICIUM_REQUIRE_BUNDLED_RUNTIME", "1");
    }
    if cfg!(target_os = "windows") {
        let python_dir = repo_root.join("tools").join("python");
        if python_dir.exists() {
            path_entries.push(python_dir);
        }
    } else {
        let site_packages = repo_root.join("tools").join("python").join("site-packages");
        command.env_remove("PYTHONHOME");
        if site_packages.exists() {
            command.env("PYTHONPATH", site_packages.display().to_string());
        } else {
            command.env_remove("PYTHONPATH");
        }
    }
    if !path_entries.is_empty() {
        let current_path = env::var("PATH").unwrap_or_default();
        let separator = if cfg!(target_os = "windows") {
            ";"
        } else {
            ":"
        };
        let prefix = path_entries
            .iter()
            .map(|path| path.display().to_string())
            .collect::<Vec<_>>()
            .join(separator);
        let next_path = format!("{}{}{}", prefix, separator, current_path);
        command.env("PATH", next_path);
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
