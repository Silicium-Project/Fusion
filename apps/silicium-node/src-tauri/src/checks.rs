//! Environment checks shown in the UI: orchestrator reachability, identity
//! mode, required paths.

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
            let integrated = body.contains("\"service\":\"p2p_node\"");
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

pub(crate) fn identity_mode_check() -> CheckItem {
    CheckItem {
        name: "Identite reseau".to_string(),
        ok: true,
        detail: "Identite Ed25519 activee en processus - aucun openssl.exe lance".to_string(),
    }
}

