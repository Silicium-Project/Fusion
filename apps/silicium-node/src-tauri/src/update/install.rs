//! Update download (hash-checked), cache for peers, and the platform-specific
//! installers (Linux AppImage swap, Windows NSIS / other platforms).

use crate::*;

pub(crate) fn download_update(release: &UpdateRelease) -> Result<PathBuf, String> {
    let updates_dir = app_state_dir().join("updates");
    fs::create_dir_all(&updates_dir).map_err(|error| error.to_string())?;
    let safe_version = release
        .version
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '.' | '-') {
                character
            } else {
                '_'
            }
        })
        .collect::<String>();
    let extension = if cfg!(target_os = "windows") {
        "exe"
    } else {
        "AppImage"
    };
    let installer = updates_dir.join(format!("silicium-node-{safe_version}.{extension}"));
    if installer.is_file() {
        let metadata = fs::metadata(&installer).map_err(|error| error.to_string())?;
        let size_matches = release.size_bytes == 0 || metadata.len() == release.size_bytes;
        if size_matches && sha256_file(&installer)? == release.sha256.trim().to_ascii_lowercase() {
            cache_update_for_peers(&installer, &release.content_id);
            return Ok(installer);
        }
    }
    let primary_download = curl_download(&release.url, &installer, 300);
    if primary_download.is_err() {
        let fallback_url = format!(
            "http://127.0.0.1:46101/updates/content/{}",
            release.content_id.trim().to_ascii_lowercase()
        );
        curl_download(&fallback_url, &installer, 600).map_err(|fallback_error| {
            format!(
                "update_download_unavailable:primary={};gossip={fallback_error}",
                primary_download
                    .err()
                    .unwrap_or_else(|| "unknown".to_string())
            )
        })?;
    }
    let metadata = fs::metadata(&installer).map_err(|error| error.to_string())?;
    if release.size_bytes > 0 && metadata.len() != release.size_bytes {
        let _ = fs::remove_file(&installer);
        return Err(format!(
            "update_size_mismatch:{}:{}",
            metadata.len(),
            release.size_bytes
        ));
    }
    let actual_hash = sha256_file(&installer)?;
    if actual_hash != release.sha256.trim().to_ascii_lowercase() {
        let _ = fs::remove_file(&installer);
        return Err("update_sha256_mismatch".to_string());
    }
    cache_update_for_peers(&installer, &release.content_id);
    Ok(installer)
}

pub(crate) fn cache_update_for_peers(installer: &Path, content_id: &str) {
    let url = format!(
        "http://127.0.0.1:46101/updates/cache/{}",
        content_id.trim().to_ascii_lowercase()
    );
    let source = format!("@{}", installer.display());
    let _ = Command::new(curl_command())
        .arg("--silent")
        .arg("--show-error")
        .arg("--fail")
        .arg("--max-time")
        .arg("300")
        .arg("--request")
        .arg("POST")
        .arg("--data-binary")
        .arg(source)
        .arg(url)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

pub(crate) fn schedule_update_install(
    installer: &Path,
    release: &UpdateRelease,
) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        return schedule_linux_appimage_install(installer, release);
    }
    #[cfg(not(target_os = "linux"))]
    {
        schedule_update_install_non_linux(installer, release)
    }
}

#[cfg(target_os = "linux")]
pub(crate) fn schedule_linux_appimage_install(
    installer: &Path,
    release: &UpdateRelease,
) -> Result<(), String> {
    // Only an AppImage can be replaced by the unprivileged node process. RPM
    // and DEB installations remain package-manager managed and must not be
    // overwritten behind the user's back.
    let appimage = env::var_os("APPIMAGE")
        .map(PathBuf::from)
        .filter(|path| path.is_file())
        .and_then(|path| path.canonicalize().ok())
        .ok_or_else(|| "automatic_update_requires_appimage".to_string())?;
    let script_path = app_state_dir().join("apply-update.sh");
    let log_path = app_state_dir().join("update-install.log");
    let script = r#"#!/bin/sh
set -u

PARENT_PID="$1"
NODE_PID="$2"
INSTALLER="$3"
APPIMAGE="$4"
REPO_ROOT="$5"
LOG_PATH="$6"
INSTALL_LOCK_PATH="$7"
FAILURE_PATH="$8"
CONTENT_ID="$9"
VERSION="${SILICIUM_UPDATE_VERSION:-unknown}"
BUILD="${SILICIUM_UPDATE_BUILD:-unknown}"

log_line() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG_PATH"
}

write_failure() {
  printf '{"contentId":"%s","version":"%s","build":"%s","error":"%s","failedAtUtc":"%s"}\n' \
    "$CONTENT_ID" "$VERSION" "$BUILD" "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$FAILURE_PATH"
}

restart_supervisor() {
  if [ -n "$REPO_ROOT" ] && [ -f "$APPIMAGE" ]; then
    nohup "$APPIMAGE" --supervisor --repo-root "$REPO_ROOT" >> "$LOG_PATH" 2>&1 </dev/null &
  fi
}

fail_update() {
  log_line "update_failed $1"
  write_failure "$1"
  rm -f "$INSTALL_LOCK_PATH"
  restart_supervisor
  exit 1
}

# The current supervisor is executing the AppImage from its temporary mount.
# Wait for it to exit before replacing the stable AppImage file and starting
# a fresh supervisor from that stable path.
while kill -0 "$PARENT_PID" 2>/dev/null; do
  sleep 0.25
done

case "$NODE_PID" in
  ''|0|*[!0-9]*) ;;
  *)
    kill -TERM "$NODE_PID" 2>/dev/null || true
    attempts=0
    while kill -0 "$NODE_PID" 2>/dev/null && [ "$attempts" -lt 40 ]; do
      sleep 0.25
      attempts=$((attempts + 1))
    done
    kill -KILL "$NODE_PID" 2>/dev/null || true
    ;;
esac

if [ -n "$REPO_ROOT" ]; then
  rm -f "$REPO_ROOT/.silicium/node-app/silicium-node.pid"
fi
if [ ! -f "$INSTALLER" ]; then
  fail_update "linux_update_artifact_missing"
fi
if [ ! -w "$(dirname "$APPIMAGE")" ]; then
  fail_update "linux_appimage_not_writable"
fi

temporary_appimage="$APPIMAGE.new.$$"
if ! cp "$INSTALLER" "$temporary_appimage"; then
  fail_update "linux_appimage_copy_failed"
fi
if ! chmod 0755 "$temporary_appimage"; then
  rm -f "$temporary_appimage"
  fail_update "linux_appimage_permission_failed"
fi
if ! mv -f "$temporary_appimage" "$APPIMAGE"; then
  rm -f "$temporary_appimage"
  fail_update "linux_appimage_replace_failed"
fi

rm -f "$FAILURE_PATH" "$INSTALL_LOCK_PATH"
log_line "update_installed $APPIMAGE"
nohup "$APPIMAGE" --supervisor --repo-root "$REPO_ROOT" >> "$LOG_PATH" 2>&1 </dev/null &
exit 0
"#;
    fs::write(&script_path, script).map_err(|error| error.to_string())?;
    let runtime_root = discover_managed_runtime_root();
    let node_pid = runtime_root
        .as_ref()
        .and_then(|root| read_pid(root).ok().flatten())
        .unwrap_or(0);
    let repo_root = runtime_root
        .as_ref()
        .map(|root| root.display().to_string())
        .unwrap_or_default();
    let mut command = Command::new("sh");
    command
        .arg(&script_path)
        .arg(std::process::id().to_string())
        .arg(node_pid.to_string())
        .arg(installer)
        .arg(&appimage)
        .arg(&repo_root)
        .arg(&log_path)
        .arg(update_install_lock_path())
        .arg(update_install_failure_path())
        .arg(&release.content_id)
        .env("SILICIUM_UPDATE_VERSION", &release.version)
        .env("SILICIUM_UPDATE_BUILD", &release.build)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command.spawn().map_err(|error| error.to_string())?;
    release_update_lock();
    std::process::exit(0);
}

#[cfg(not(target_os = "linux"))]
pub(crate) fn schedule_update_install_non_linux(
    installer: &Path,
    release: &UpdateRelease,
) -> Result<(), String> {
    if !cfg!(target_os = "windows") {
        return Err(format!(
            "automatic_update_installer_not_available:{}",
            update_platform()
        ));
    }
    let script_path = app_state_dir().join("apply-update.ps1");
    let log_path = app_state_dir().join("update-install.log");
    let script = r#"param(
  [int]$ParentPid,
  [int]$NodePid,
  [string]$Installer,
  [string]$Executable,
  [string]$RepoRoot,
  [string]$LogPath,
  [string]$InstallLockPath,
  [string]$FailurePath,
  [string]$ContentId,
  [string]$Version,
  [string]$Build
)
$ErrorActionPreference = 'Stop'
try {
  while (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 250 }
  if ($NodePid -gt 0) { & taskkill.exe /PID $NodePid /T /F | Out-Null }
  if ($RepoRoot) {
    Get-CimInstance Win32_Process | Where-Object {
      $_.ProcessId -ne $PID -and
      $_.CommandLine -and
      $_.CommandLine.IndexOf('silicium node start', [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
      $_.CommandLine.IndexOf($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    } | ForEach-Object {
      & taskkill.exe /PID $_.ProcessId /T /F | Out-Null
      Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) stale_node_runtime_stopped pid=$($_.ProcessId)"
    }
    Remove-Item -LiteralPath (Join-Path $RepoRoot '.silicium\node-app\silicium-node.pid') -Force -ErrorAction SilentlyContinue
  }
  Get-Process -Name 'silicium-node' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
  $process = $null
  for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
      $process = Start-Process -FilePath $Installer -ArgumentList '/S' -Wait -PassThru
      break
    } catch {
      Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) installer_launch_retry attempt=$attempt error=$($_.Exception.Message)"
      if ($attempt -eq 30) { throw }
      Start-Sleep -Seconds 2
    }
  }
  if ($null -eq $process) { throw 'installer_not_started' }
  if ($process.ExitCode -ne 0) { throw "installer_exit_$($process.ExitCode)" }
  Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) update_installed $Installer"
  if ($RepoRoot -and (Test-Path -LiteralPath (Join-Path $RepoRoot '.silicium\node-app\service-config.env'))) {
    Start-Process -FilePath $Executable -ArgumentList '--background' -WindowStyle Hidden
    Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) notification_shell_restarted $RepoRoot"
  } else {
    Start-Process -FilePath $Executable
  }
} catch {
  $errorMessage = $_.Exception.Message
  Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) update_failed $errorMessage"
  if ($FailurePath) {
    $failure = @{
      contentId = $ContentId
      version = $Version
      build = $Build
      error = $errorMessage
      failedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Compress
    Set-Content -LiteralPath $FailurePath -Value $failure -Encoding UTF8
  }
  if ($RepoRoot -and (Test-Path -LiteralPath (Join-Path $RepoRoot '.silicium\node-app\service-config.env'))) {
    $quotedRepoRoot = '"' + $RepoRoot + '"'
    Start-Process -FilePath $Executable -ArgumentList '--supervisor', '--repo-root', $quotedRepoRoot -WindowStyle Hidden
    Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) supervisor_recovered_after_update_failure $RepoRoot"
  }
  Start-Process -FilePath $Executable
  exit 1
} finally {
  if ($InstallLockPath) {
    Remove-Item -LiteralPath $InstallLockPath -Force -ErrorAction SilentlyContinue
  }
}
"#;
    fs::write(&script_path, script).map_err(|error| error.to_string())?;
    let executable = env::current_exe().map_err(|error| error.to_string())?;
    let runtime_root = discover_managed_runtime_root();
    let node_pid = runtime_root
        .as_ref()
        .and_then(|root| read_pid(root).ok().flatten())
        .unwrap_or(0);
    let repo_root = runtime_root
        .as_ref()
        .map(|root| root.display().to_string())
        .unwrap_or_default();
    let mut command = Command::new("powershell.exe");
    command
        .arg("-NoProfile")
        .arg("-NonInteractive")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-File")
        .arg(&script_path)
        .arg("-ParentPid")
        .arg(std::process::id().to_string())
        .arg("-NodePid")
        .arg(node_pid.to_string())
        .arg("-Installer")
        .arg(installer)
        .arg("-Executable")
        .arg(executable)
        .arg("-RepoRoot")
        .arg(repo_root)
        .arg("-LogPath")
        .arg(log_path)
        .arg("-InstallLockPath")
        .arg(update_install_lock_path())
        .arg("-FailurePath")
        .arg(update_install_failure_path())
        .arg("-ContentId")
        .arg(&release.content_id)
        .arg("-Version")
        .arg(&release.version)
        .arg("-Build")
        .arg(&release.build)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    configure_detached_process(&mut command);
    command.spawn().map_err(|error| error.to_string())?;
    release_update_lock();
    std::process::exit(0);
}
