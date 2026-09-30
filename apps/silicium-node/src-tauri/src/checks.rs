//! Environment checks shown in the UI: orchestrator reachability, Python,
//! identity mode, required paths.

use crate::*;

pub(crate) fn orchestrator_check(url: &str) -> CheckItem {
    let normalized = match normalize_orchestrator_url(url) {
        Ok(value) => value,
        Err(error) => {
            return CheckItem {
                name: "Orchestrateur".to_string(),
                ok: false,
                detail: error,
            };
        }
    };
    let health_url = format!("{}/healthz", normalized.trim_end_matches('/'));
    let curl = if cfg!(target_os = "windows") {
        "curl.exe"
    } else {
        "curl"
    };
    let mut command = Command::new(curl);
    crate::http::apply_tls_options(&mut command);
    command
        .args([
            "--fail",
            "--silent",
            "--show-error",
            "--connect-timeout",
            "5",
            "--max-time",
            "8",
        ])
        .arg(&health_url)
        .stdin(Stdio::null());
    configure_detached_process(&mut command);
    match command.output() {
        Ok(output) if output.status.success() => {
            let body = String::from_utf8_lossy(&output.stdout);
            let integrated = body.contains("\"service\":\"network_node\"");
            CheckItem {
                name: "Orchestrateur".to_string(),
                ok: integrated,
                detail: if integrated {
                    format!("{} repond avec le daemon reseau integre", normalized)
                } else {
                    format!("{} repond avec un service inattendu", normalized)
                },
            }
        }
        Ok(output) => {
            let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
            CheckItem {
                name: "Orchestrateur".to_string(),
                ok: false,
                detail: if detail.is_empty() {
                    format!("{} injoignable", normalized)
                } else {
                    format!("{} injoignable: {}", normalized, detail)
                },
            }
        }
        Err(error) => CheckItem {
            name: "Orchestrateur".to_string(),
            ok: false,
            detail: format!("verification impossible: {}", error),
        },
    }
}

pub(crate) fn python_command_check(repo_root: &Path) -> CheckItem {
    let python = python_launcher(repo_root);
    let mut process = Command::new(python);
    configure_python_command(&mut process, repo_root);
    process.arg("--version").stdin(Stdio::null());
    configure_detached_process(&mut process);
    match process.output() {
        Ok(output) if output.status.success() => CheckItem {
            name: "Python".to_string(),
            ok: true,
            detail: String::from_utf8_lossy(if output.stdout.is_empty() {
                &output.stderr
            } else {
                &output.stdout
            })
            .trim()
            .to_string(),
        },
        Ok(output) => CheckItem {
            name: "Python".to_string(),
            ok: false,
            detail: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        },
        Err(error) => CheckItem {
            name: "Python".to_string(),
            ok: false,
            detail: error.to_string(),
        },
    }
}

pub(crate) fn configure_python_command(command: &mut Command, repo_root: &Path) {
    if !cfg!(target_os = "linux") {
        return;
    }
    // AppImage's launcher exports PYTHONHOME/PYTHONPATH for its bundled
    // partial Python tree. The node uses the host interpreter with the
    // packaged third-party modules instead.
    command.env_remove("PYTHONHOME");
    let site_packages = repo_root.join("tools").join("python").join("site-packages");
    if site_packages.exists() {
        command.env("PYTHONPATH", site_packages.display().to_string());
    } else {
        command.env_remove("PYTHONPATH");
    }
}

pub(crate) fn identity_mode_check() -> CheckItem {
    CheckItem {
        name: "Identite reseau".to_string(),
        ok: true,
        detail: "Identite Ed25519 activee en processus - aucun openssl.exe lance".to_string(),
    }
}

pub(crate) fn path_check(name: &str, path: &Path) -> CheckItem {
    CheckItem {
        name: name.to_string(),
        ok: path.exists(),
        detail: path.display().to_string(),
    }
}
