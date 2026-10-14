#!/usr/bin/env bash
set -euo pipefail

SILICIUM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export SILICIUM_ROOT
RELEASE_CHANNEL="${SILICIUM_RELEASE_CHANNEL:-prod}"
CHANNEL_TOOL="$SILICIUM_ROOT/deploy/release/channel.py"
python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" >/dev/null
channel_config_dir="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field config_dir)"
channel_data_root="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field data_dir)"
channel_public_base_url="$(python3 "$CHANNEL_TOOL" "$RELEASE_CHANNEL" --field public_base_url)"
CONFIG_DIR="${SILICIUM_CONFIG_DIR:-$channel_config_dir}"
DATA_ROOT="${SILICIUM_DATA_ROOT:-$channel_data_root}"
CONFIG_PATH="${SILICIUM_UPDATE_CHANNELS_CONFIG:-$CONFIG_DIR/update-channels.env}"
export SILICIUM_CONFIG_DIR="$CONFIG_DIR"
export SILICIUM_DATA_ROOT="$DATA_ROOT"
if [[ -f "$CONFIG_PATH" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$CONFIG_PATH"
  set +a
fi
CONFIG_DIR="${SILICIUM_CONFIG_DIR:-$CONFIG_DIR}"
DATA_ROOT="${SILICIUM_DATA_ROOT:-$DATA_ROOT}"

export SILICIUM_DOWNLOADS_DIR="${SILICIUM_DOWNLOADS_DIR:-$DATA_ROOT/downloads}"
if [[ -z "${SILICIUM_DOWNLOAD_BASE_URL:-}" || "$SILICIUM_DOWNLOAD_BASE_URL" == "https://vps-910c1dbc.vps.ovh.net/downloads" ]]; then
  export SILICIUM_DOWNLOAD_BASE_URL="$channel_public_base_url/downloads"
fi
DEFAULT_DEV_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$SILICIUM_ROOT/apps/silicium-node/package.json")"
DEFAULT_PROD_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$SILICIUM_ROOT/apps/silicium-node/src-tauri/tauri.prod.conf.json")"
export SILICIUM_DEV_VERSION="${SILICIUM_DEV_VERSION:-$DEFAULT_DEV_VERSION}"
export SILICIUM_PROD_VERSION="${SILICIUM_PROD_VERSION:-$DEFAULT_PROD_VERSION}"
export SILICIUM_RELEASE_BUILD="${SILICIUM_RELEASE_BUILD:-}"
export SILICIUM_DEV_RELEASE_BUILD="${SILICIUM_DEV_RELEASE_BUILD:-$SILICIUM_RELEASE_BUILD}"
export SILICIUM_PROD_RELEASE_BUILD="${SILICIUM_PROD_RELEASE_BUILD:-$SILICIUM_RELEASE_BUILD}"
export SILICIUM_DEV_CHECK_INTERVAL_SECONDS="${SILICIUM_DEV_CHECK_INTERVAL_SECONDS:-30}"
export SILICIUM_PROD_CHECK_INTERVAL_SECONDS="${SILICIUM_PROD_CHECK_INTERVAL_SECONDS:-21600}"
export SILICIUM_UPDATE_SIGNING_KEY="${SILICIUM_UPDATE_SIGNING_KEY:-$CONFIG_DIR/update-signing-key.pem}"
export SILICIUM_RELEASE_CHANNEL="$RELEASE_CHANNEL"
python3 "$SILICIUM_ROOT/deploy/release/channel.py" "$SILICIUM_RELEASE_CHANNEL" >/dev/null

mkdir -p "$SILICIUM_DOWNLOADS_DIR"

python3 - <<'PY'
import hashlib
import base64
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

downloads = Path(os.environ["SILICIUM_DOWNLOADS_DIR"])
base_url = os.environ["SILICIUM_DOWNLOAD_BASE_URL"].rstrip("/")
channels = {}
manifest_path = downloads / "update-manifest.json"
try:
    existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError, OSError):
    existing_manifest = {}
existing_channels = (
    existing_manifest.get("channels", {})
    if isinstance(existing_manifest, dict) and isinstance(existing_manifest.get("channels"), dict)
    else {}
)
signing_key = Path(os.environ["SILICIUM_UPDATE_SIGNING_KEY"])
if not signing_key.is_file():
    raise SystemExit(f"update signing key not found: {signing_key}")
public_der = subprocess.run(
    ["openssl", "pkey", "-in", str(signing_key), "-pubout", "-outform", "DER"],
    check=True,
    capture_output=True,
).stdout
if len(public_der) < 32:
    raise SystemExit("update signing public key is invalid")
public_key = public_der[-32:]
signing_key_id = hashlib.sha256(public_key).hexdigest()
definitions = {
    "dev": {
        "version": os.environ["SILICIUM_DEV_VERSION"],
        "interval": int(os.environ["SILICIUM_DEV_CHECK_INTERVAL_SECONDS"]),
        "artifacts": [
            ("windows-x86_64", "silicium-node-windows-dev.exe"),
            ("linux-x86_64", "silicium-node-linux-dev.AppImage"),
        ],
    },
    "prod": {
        "version": os.environ["SILICIUM_PROD_VERSION"],
        "interval": int(os.environ["SILICIUM_PROD_CHECK_INTERVAL_SECONDS"]),
        "artifacts": [
            ("windows-x86_64", "silicium-node-windows.exe"),
            ("linux-x86_64", "silicium-node-linux.AppImage"),
        ],
    },
}
require_all_artifacts = os.environ.get("SILICIUM_UPDATE_REQUIRE_ALL_ARTIFACTS", "") == "1"
published_channel = os.environ.get("SILICIUM_RELEASE_CHANNEL", "")
if published_channel not in definitions:
    raise SystemExit(f"unsupported release channel: {published_channel}")
required_definitions = list(definitions.values()) if require_all_artifacts else [definitions[published_channel]]
# Development releases currently publish the Linux AppImage as the updater
# target; native .deb/.rpm packages remain direct-install assets. Production
# must always contain all three Linux bundles plus the Windows installer.
required_artifacts = [
    (platform, filename)
    for definition in required_definitions
    for platform, filename in definition["artifacts"]
    if published_channel == "prod" or filename.endswith(".AppImage")
]
missing_artifacts = [
    str(downloads / filename)
    for _platform, filename in required_artifacts
    if not (downloads / filename).is_file()
]
if missing_artifacts:
    raise SystemExit("required node artifacts are missing: " + ", ".join(missing_artifacts))


releases = []
existing_releases = existing_manifest.get("releases", []) if isinstance(existing_manifest, dict) else []
if not isinstance(existing_releases, list):
    existing_releases = []

for channel, definition in definitions.items():
    channel_releases = []
    version = definition["version"]
    interval = definition["interval"]
    for platform, filename in definition["artifacts"]:
        artifact = downloads / filename
        if not artifact.is_file():
            continue
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        content_id = digest
        requested_build = os.environ.get(
            f"SILICIUM_{channel.upper()}_RELEASE_BUILD",
            os.environ.get("SILICIUM_RELEASE_BUILD", ""),
        ).strip()
        existing_release = next(
            (
                item
                for item in existing_releases
                if isinstance(item, dict)
                and str(item.get("channel", "")).strip() == channel
                and str(item.get("platform", "")).strip().lower() == platform
                and str(item.get("url", "")).rstrip("/").endswith("/" + filename)
            ),
            None,
        )
        if existing_release is None:
            legacy_release = existing_channels.get(channel, {})
            if (
                isinstance(legacy_release, dict)
                and str(legacy_release.get("url", "")).rstrip("/").endswith("/" + filename)
            ):
                existing_release = legacy_release
        unchanged_artifact = (
            isinstance(existing_release, dict)
            and str(existing_release.get("version", "")).strip() == version
            and str(existing_release.get("sha256", "")).strip().lower() == digest
            and int(existing_release.get("size_bytes", 0) or 0) == artifact.stat().st_size
        )
        release_build = requested_build
        if not release_build and unchanged_artifact:
            release_build = str(existing_release.get("build", "")).strip()
        if not release_build:
            release_build = subprocess.run(
                ["git", "-C", os.environ["SILICIUM_ROOT"], "rev-parse", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
        release = {
            "version": version,
            "build": release_build,
            "channel": channel,
            "platform": platform,
            "url": f"{base_url}/{filename}",
            "sha256": digest,
            "content_id": content_id,
            "size_bytes": artifact.stat().st_size,
            "auto_install": True,
            "check_interval_seconds": max(15, interval),
            "signing_key_id": signing_key_id,
        }
        canonical = "\n".join(
            [
                "silicium-update-v1",
                release["channel"],
                release["platform"],
                release["version"],
                release["sha256"],
                str(release["size_bytes"]),
                release["url"],
                release["content_id"],
                "",
            ]
        ).encode("utf-8")
        with tempfile.NamedTemporaryFile() as signing_input:
            signing_input.write(canonical)
            signing_input.flush()
            signature = subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(signing_key), "-in", signing_input.name],
                check=True,
                capture_output=True,
            ).stdout
        release["signature"] = base64.b64encode(signature).decode("ascii")
        channel_releases.append(release)
        releases.append(release)
    if channel_releases:
        channels[channel] = next(
            (release for release in channel_releases if release["platform"].startswith("windows-")),
            channel_releases[0],
        )

payload = {
    "schema_version": 1,
    "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "publisher_channel": os.environ["SILICIUM_RELEASE_CHANNEL"],
    "publisher_build": os.environ.get("SILICIUM_RELEASE_BUILD", ""),
    "channels": channels,
    "releases": releases,
}
temporary = downloads / ".update-manifest.json.tmp"
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
temporary.replace(manifest_path)
PY
