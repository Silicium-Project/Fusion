#!/usr/bin/env bash
set -euo pipefail

RUNNER_USER="${SILICIUM_GHA_RUNNER_USER:-github-runner}"
RUNNER_ROOT="${SILICIUM_GHA_RUNNER_DIR:-/opt/github-runner}"
RUNNER_LABELS="${SILICIUM_GHA_RUNNER_LABELS:-self-hosted,fusion-linux}"
BOOTSTRAP_TOKEN="${GITHUB_RUNNER_BOOTSTRAP_TOKEN:-}"
REPOS=(BackEnd FrontEnd)

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo -E bash deploy/linux/bootstrap-submodule-runners.sh" >&2
  exit 1
fi
if [[ -z "$BOOTSTRAP_TOKEN" ]]; then
  echo "GITHUB_RUNNER_BOOTSTRAP_TOKEN is required." >&2
  exit 1
fi
if ! id -u "$RUNNER_USER" >/dev/null 2>&1; then
  echo "Runner user does not exist: $RUNNER_USER" >&2
  exit 1
fi

install -d -m 0755 /var/lock
exec 9>/var/lock/silicium-submodule-runners.lock
flock 9

runner_version=""
runner_archive=""
runner_download=""

ensure_runner_package() {
  if [[ -n "$runner_archive" ]]; then
    return 0
  fi

  runner_version="$(curl -fsSL \
    -H 'Accept: application/vnd.github+json' \
    https://api.github.com/repos/actions/runner/releases/latest |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"].lstrip("v"))')"
  runner_archive="actions-runner-linux-x64-${runner_version}.tar.gz"
  runner_download="/tmp/${runner_archive}"
  if [[ ! -s "$runner_download" ]]; then
    curl -fsSL -o "$runner_download" \
      "https://github.com/actions/runner/releases/download/v${runner_version}/${runner_archive}"
  fi
}

registration_token() {
  local repo="$1"
  curl -fsSL -X POST \
    -H 'Accept: application/vnd.github+json' \
    -H "Authorization: Bearer ${BOOTSTRAP_TOKEN}" \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "https://api.github.com/repos/Silicium-Project/${repo}/actions/runners/registration-token" |
    python3 -c 'import json, sys; print(json.load(sys.stdin)["token"])'
}

for repo in "${REPOS[@]}"; do
  slug="$(printf '%s' "$repo" | tr '[:upper:]' '[:lower:]')"
  runner_dir="${RUNNER_ROOT}-${slug}"
  runner_name="fusion-vps-${slug}"
  runner_url="https://github.com/Silicium-Project/${repo}"

  if [[ ! -x "$runner_dir/config.sh" ]]; then
    ensure_runner_package
    install -d -o "$RUNNER_USER" -g "$RUNNER_USER" "$runner_dir"
    tar -xzf "$runner_download" -C "$runner_dir"
    chown -R "$RUNNER_USER":"$RUNNER_USER" "$runner_dir"
  fi

  if [[ ! -f "$runner_dir/.runner" ]]; then
    token="$(registration_token "$repo")"
    sudo -u "$RUNNER_USER" env \
      RUNNER_DIR="$runner_dir" \
      RUNNER_URL="$runner_url" \
      RUNNER_TOKEN="$token" \
      RUNNER_NAME="$runner_name" \
      RUNNER_LABELS="$RUNNER_LABELS" \
      bash -c '
        set -euo pipefail
        cd "$RUNNER_DIR"
        ./config.sh --unattended \
          --url "$RUNNER_URL" \
          --token "$RUNNER_TOKEN" \
          --name "$RUNNER_NAME" \
          --labels "$RUNNER_LABELS" \
          --work _work \
          --replace
      '
  fi

  if [[ -x "$runner_dir/svc.sh" ]]; then
    cd "$runner_dir"
    if ! systemctl is-active --quiet "actions.runner.Silicium-Project-${repo}.${runner_name}.service"; then
      ./svc.sh install "$RUNNER_USER" >/dev/null 2>&1 || true
      ./svc.sh start
    fi
  else
    echo "Runner service helper not found: $runner_dir/svc.sh" >&2
    exit 1
  fi
done

unset BOOTSTRAP_TOKEN
echo "BackEnd and FrontEnd self-hosted runners are configured on this VPS."
