//! Small helpers around the system `curl` binary, file hashing and UTC time.

use crate::*;

pub(crate) fn curl_get(url: &str, timeout_seconds: u64) -> Result<String, String> {
    let mut command = Command::new(curl_command());
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
