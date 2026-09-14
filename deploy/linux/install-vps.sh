#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/silicium}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/install-vps.sh $ROOT" >&2
  exit 1
fi

apt-get update
apt-get install -y \
  ca-certificates \
  curl \
  git \
  nginx \
  docker.io \
  postgresql \
  postgresql-client \
  sqlite3 \
  openssl \
  python3 \
  python3-venv \
  python3-pip \
  python3-cryptography \
  python3-protobuf \
  python3-zmq \
  apt-utils \
  createrepo-c \
  gpg \
  golang-go

if apt-cache show docker-compose-plugin >/dev/null 2>&1; then
  apt-get install -y docker-compose-plugin
elif apt-cache show docker-compose-v2 >/dev/null 2>&1; then
  apt-get install -y docker-compose-v2
else
  echo "No Docker Compose v2 package is available in the configured apt repositories." >&2
  echo "Enable the Docker or Ubuntu repository providing docker-compose-v2, then rerun this installer." >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1 || [[ "$(node -p 'Number(process.versions.node.split(".")[0])')" -lt 20 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

mkdir -p /etc/silicium /var/lib/silicium/site /var/lib/silicium/network /var/lib/silicium/solana "$ROOT/bin"
systemctl enable --now docker

if [[ ! -d "$ROOT/.git" ]]; then
  echo "Expected repository cloned at $ROOT." >&2
  echo "Clone it first, or pass the existing repo path as first argument." >&2
  exit 1
fi

install_github_actions_runner() {
  local runner_url="${SILICIUM_GHA_RUNNER_URL:-}"
  local runner_token="${SILICIUM_GHA_RUNNER_TOKEN:-}"
  local runner_name="${SILICIUM_GHA_RUNNER_NAME:-fusion-vps}"
  local runner_labels="${SILICIUM_GHA_RUNNER_LABELS:-self-hosted,fusion-linux,fusion-bootstrap}"
  local runner_user="${SILICIUM_GHA_RUNNER_USER:-github-runner}"
  local runner_dir="${SILICIUM_GHA_RUNNER_DIR:-/opt/github-runner}"
  local runner_version="${SILICIUM_GHA_RUNNER_VERSION:-}"
  local runner_tarball="actions-runner-linux-x64-${runner_version}.tar.gz"

  if [[ -z "$runner_url" || -z "$runner_token" ]]; then
    echo "Skipping GitHub Actions runner installation (set SILICIUM_GHA_RUNNER_URL and SILICIUM_GHA_RUNNER_TOKEN to enable it)."
    return 0
  fi

  if [[ -z "$runner_version" ]]; then
    runner_version="$(python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("https://api.github.com/repos/actions/runner/releases/latest") as response:
    payload = json.load(response)

tag = str(payload["tag_name"]).strip()
print(tag.lstrip("v"))
PY
)"
    runner_tarball="actions-runner-linux-x64-${runner_version}.tar.gz"
  fi

  if ! id -u "$runner_user" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "$runner_dir" --shell /bin/bash "$runner_user"
  fi
  usermod -aG docker "$runner_user"

  install -d -o "$runner_user" -g "$runner_user" "$runner_dir"
  chown -R "$runner_user":"$runner_user" "$runner_dir"

  if [[ ! -x "$runner_dir/config.sh" ]]; then
    sudo -u "$runner_user" bash -lc "
      set -euo pipefail
      cd '$runner_dir'
      curl -fsSLo '$runner_tarball' \
        'https://github.com/actions/runner/releases/download/v${runner_version}/$runner_tarball'
      tar xzf '$runner_tarball'
      rm -f '$runner_tarball'
    "
  fi

  sudo -u "$runner_user" bash -lc "
    set -euo pipefail
    cd '$runner_dir'
    if [[ -f .runner ]]; then
      ./config.sh remove --token '$runner_token' >/dev/null 2>&1 || true
    fi
    ./config.sh --unattended \
      --url '$runner_url' \
      --token '$runner_token' \
      --name '$runner_name' \
      --labels '$runner_labels' \
      --replace
  "

  if [[ -x "$runner_dir/svc.sh" ]]; then
    "$runner_dir/svc.sh" stop >/dev/null 2>&1 || true
    "$runner_dir/svc.sh" uninstall >/dev/null 2>&1 || true
    "$runner_dir/svc.sh" install "$runner_user"
    "$runner_dir/svc.sh" start
  else
    echo "Runner service helper not found in $runner_dir." >&2
    echo "The runner was configured, but you need to start it manually with '$runner_dir/run.sh'." >&2
  fi

  unset runner_token
}

if [[ "${SILICIUM_INSTALL_GITHUB_ACTIONS_RUNNER:-0}" == "1" ]]; then
  install_github_actions_runner
fi

echo "Base VPS dependencies installed."
echo "Next:"
echo "  sudo cp deploy/env/*.example.env /etc/silicium/"
echo "  sudo bash deploy/linux/migrate-postgres-to-compose.sh $ROOT"
