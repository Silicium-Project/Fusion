#!/usr/bin/env bash
set -euo pipefail

SILICIUM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_PATH="${SILICIUM_UPDATE_CHANNELS_CONFIG:-/etc/silicium/update-channels.env}"
if [[ -f "$CONFIG_PATH" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$CONFIG_PATH"
  set +a
fi

export SILICIUM_DOWNLOADS_DIR="${SILICIUM_DOWNLOADS_DIR:-/var/lib/silicium/downloads}"
export SILICIUM_DOWNLOAD_BASE_URL="${SILICIUM_DOWNLOAD_BASE_URL:-https://vps-910c1dbc.vps.ovh.net/downloads}"
DEFAULT_DEV_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$SILICIUM_ROOT/apps/silicium-node/package.json")"
export SILICIUM_DEV_VERSION="${SILICIUM_DEV_VERSION:-$DEFAULT_DEV_VERSION}"
export SILICIUM_PROD_VERSION="${SILICIUM_PROD_VERSION:-0.2.17}"
export SILICIUM_RELEASE_BUILD="${SILICIUM_RELEASE_BUILD:-$(git -C "$SILICIUM_ROOT" rev-parse HEAD 2>/dev/null || true)}"
export SILICIUM_DEV_CHECK_INTERVAL_SECONDS="${SILICIUM_DEV_CHECK_INTERVAL_SECONDS:-30}"
export SILICIUM_PROD_CHECK_INTERVAL_SECONDS="${SILICIUM_PROD_CHECK_INTERVAL_SECONDS:-21600}"
export SILICIUM_UPDATE_SIGNING_KEY="${SILICIUM_UPDATE_SIGNING_KEY:-/etc/silicium/update-signing-key.pem}"
export SILICIUM_UPDATE_P2P_DIR="${SILICIUM_UPDATE_P2P_DIR:-/var/lib/silicium/network/orchestrator/export/p2p}"
export SILICIUM_UPDATE_GOSSIP_URL="${SILICIUM_UPDATE_GOSSIP_URL:-http://127.0.0.1:46100/gossip/publish}"
export SILICIUM_MESH_KEY="${SILICIUM_MESH_KEY:-demo-mesh}"
export SILICIUM_UPDATE_PUBLISHER_IDENTITY_KEY="${SILICIUM_UPDATE_PUBLISHER_IDENTITY_KEY:-/var/lib/silicium/update-publisher/peer_identity_ed25519.pem}"
export SILICIUM_UPDATE_GOSSIP_REQUIRED="${SILICIUM_UPDATE_GOSSIP_REQUIRED:-1}"

mkdir -p "$SILICIUM_DOWNLOADS_DIR"

python3 - <<'PY'
import hashlib
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path

downloads = Path(os.environ["SILICIUM_DOWNLOADS_DIR"])
base_url = os.environ["SILICIUM_DOWNLOAD_BASE_URL"].rstrip("/")
channels = {}
signing_key = Path(os.environ["SILICIUM_UPDATE_SIGNING_KEY"])
p2p_dir = Path(os.environ["SILICIUM_UPDATE_P2P_DIR"])
if not signing_key.is_file():
    raise SystemExit(f"update signing key not found: {signing_key}")
p2p_dir.mkdir(parents=True, exist_ok=True)
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
    "dev": (os.environ["SILICIUM_DEV_VERSION"], "silicium-node-windows-dev.exe", int(os.environ["SILICIUM_DEV_CHECK_INTERVAL_SECONDS"])),
    "prod": (os.environ["SILICIUM_PROD_VERSION"], "silicium-node-windows.exe", int(os.environ["SILICIUM_PROD_CHECK_INTERVAL_SECONDS"])),
}


def signed_peer_headers(url: str, body: bytes) -> dict[str, str]:
    private_key = Path(os.environ["SILICIUM_UPDATE_PUBLISHER_IDENTITY_KEY"])
    public_key = private_key.with_suffix(".pub.pem")
    private_key.parent.mkdir(parents=True, exist_ok=True)
    if not private_key.is_file():
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private_key)],
            check=True,
            capture_output=True,
        )
        private_key.chmod(0o600)
    if not public_key.is_file():
        subprocess.run(
            ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
            check=True,
            capture_output=True,
        )
    public_pem = public_key.read_bytes()
    public_key_b64 = base64.b64encode(public_pem).decode("ascii")
    identity_id = hashlib.sha256(public_pem).hexdigest()[:32]
    node_id = "update-publisher"
    timestamp = str(int(time.time()))
    body_hash = hashlib.sha256(body).hexdigest()
    parsed = urlsplit(url)
    request_path = parsed.path or "/"
    if parsed.query:
        request_path += "?" + parsed.query
    signing_payload = "\n".join(
        ["POST", request_path, timestamp, body_hash, node_id, identity_id]
    ).encode("utf-8")
    with tempfile.NamedTemporaryFile() as signing_input:
        signing_input.write(signing_payload)
        signing_input.flush()
        signature = subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(private_key), "-in", signing_input.name],
            check=True,
            capture_output=True,
        ).stdout.hex()
    return {
        "Content-Type": "application/json",
        "X-Silicium-Node-Id": node_id,
        "X-Silicium-Identity-Id": identity_id,
        "X-Silicium-Public-Key": public_key_b64,
        "X-Silicium-Timestamp": timestamp,
        "X-Silicium-Body-Hash": body_hash,
        "X-Silicium-Signature": signature,
    }

for channel, (version, filename, interval) in definitions.items():
    artifact = downloads / filename
    if not artifact.is_file():
        continue
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    content_id = digest
    cached_artifact = p2p_dir / content_id
    if not cached_artifact.is_file() or cached_artifact.stat().st_size != artifact.stat().st_size:
        temporary_artifact = p2p_dir / f".{content_id}.tmp"
        shutil.copyfile(artifact, temporary_artifact)
        if hashlib.sha256(temporary_artifact.read_bytes()).hexdigest() != digest:
            temporary_artifact.unlink(missing_ok=True)
            raise SystemExit(f"P2P update cache verification failed: {artifact}")
        temporary_artifact.replace(cached_artifact)
    release = {
        "version": version,
        "build": os.environ.get("SILICIUM_RELEASE_BUILD", "").strip(),
        "channel": channel,
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
    channels[channel] = release

payload = {
    "schema_version": 1,
    "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "channels": channels,
}
temporary = downloads / ".update-manifest.json.tmp"
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
temporary.replace(downloads / "update-manifest.json")

gossip_url = os.environ.get("SILICIUM_UPDATE_GOSSIP_URL", "").strip()
mesh_key = os.environ.get("SILICIUM_MESH_KEY", "").strip()
if gossip_url:
    gossip_failures = []
    for release in channels.values():
        body = json.dumps({"topic": "software_update", "payload": release}, separators=(",", ":")).encode("utf-8")
        headers = signed_peer_headers(gossip_url, body)
        if mesh_key:
            headers["Authorization"] = f"Bearer {mesh_key}"
        request = urllib.request.Request(gossip_url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status not in {200, 202}:
                    raise RuntimeError(f"HTTP {response.status}")
        except Exception as exc:
            gossip_failures.append(f"{release['channel']}: {exc}")
            print(f"warning: update gossip publication failed for {release['channel']}: {exc}", file=sys.stderr)
    if gossip_failures and os.environ.get("SILICIUM_UPDATE_GOSSIP_REQUIRED", "1") == "1":
        raise SystemExit("update gossip publication required: " + "; ".join(gossip_failures))
PY
