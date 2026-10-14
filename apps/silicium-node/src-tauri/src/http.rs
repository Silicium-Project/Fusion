//! Small helpers around the system `curl` binary, file hashing and UTC time.

use crate::*;

pub(crate) fn curl_get(url: &str, timeout_seconds: u64) -> Result<String, String> {
    let mut command = Command::new(curl_command());
    apply_tls_options(&mut command);
    command
        .arg("-4")
        .arg("--fail")
        .arg("--silent")
        .arg("--show-error")
        .arg("--location")
        .arg("--max-time")
        .arg(timeout_seconds.to_string())
        .arg(url)
        .stdin(Stdio::null());
    configure_detached_process(&mut command);
    let output = command
        .output()
        .map_err(|error| format!("curl_start_failed:{error}"))?;
    if !output.status.success() {
        return Err(format!(
            "curl_failed:{}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

pub(crate) fn curl_download(url: &str, target: &Path, timeout_seconds: u64) -> Result<(), String> {
    let mut command = Command::new(curl_command());
    apply_tls_options(&mut command);
    command
        .arg("-4")
        .arg("--fail")
        .arg("--silent")
        .arg("--show-error")
        .arg("--location")
        .arg("--max-time")
        .arg(timeout_seconds.to_string())
        .arg("--output")
        .arg(target)
        .arg(url)
        .stdin(Stdio::null());
    configure_detached_process(&mut command);
    let output = command
        .output()
        .map_err(|error| format!("curl_start_failed:{error}"))?;
    if !output.status.success() {
        return Err(format!(
            "curl_failed:{}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(())
}

/// On Windows, curl uses Schannel, which fails when the certificate revocation
/// status cannot be checked (CRYPT_E_NO_REVOCATION_CHECK); the dev channel
/// certificate has no reachable revocation service. The certificate itself is
/// still verified, and updates are authenticated by the signed manifest.
/// `--ssl-no-revoke` (curl >= 7.44) is used rather than
/// `--ssl-revoke-best-effort` (curl >= 7.70) so older Windows 10 curl works.
pub(crate) fn apply_tls_options(command: &mut Command) {
    if cfg!(target_os = "windows") {
        command.arg("--ssl-no-revoke");
    }
}

pub(crate) fn curl_command() -> &'static str {
    if cfg!(target_os = "windows") {
        "curl.exe"
    } else {
        "curl"
    }
}

pub(crate) fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(|error| error.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

pub(crate) fn current_utc() -> String {
    DateTime::<Utc>::from(SystemTime::now()).to_rfc3339_opts(SecondsFormat::Secs, true)
}
