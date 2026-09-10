#!/usr/bin/env bash
set -euo pipefail

RUNNER_USER="${SILICIUM_GHA_RUNNER_USER:-github-runner}"
RUNNER_ROOT="${SILICIUM_GHA_RUNNER_DIR:-/opt/github-runner}"
RUNNER_LABELS="${SILICIUM_GHA_RUNNER_LABELS:-self-hosted,fusion-linux}"
BOOTSTRAP_TOKEN="${GITHUB_RUNNER_BOOTSTRAP_TOKEN:-}"
REPOS=(BackEnd FrontEnd)
EXTRA_RUNNER_COUNT="${SILICIUM_EXTRA_RUNNER_COUNT:-1}"

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

configure_runner_runtime() {
  local docker_path docker_compose_path sudoers_file deps_marker audio_package
  local linux_build_deps_marker fuse_package

  docker_path="$(command -v docker || true)"
  docker_compose_path="$(command -v docker-compose || true)"
  if [[ -n "$docker_path" ]]; then
    sudoers_file="/etc/sudoers.d/silicium-${RUNNER_USER}-docker"
    {
      printf '%s ALL=(root) NOPASSWD: %s\n' "$RUNNER_USER" "$docker_path"
      if [[ -n "$docker_compose_path" ]]; then
        printf '%s ALL=(root) NOPASSWD: %s\n' "$RUNNER_USER" "$docker_compose_path"
      fi
    } > "$sudoers_file"
    chmod 0440 "$sudoers_file"
    visudo -cf "$sudoers_file"
  fi

  deps_marker="/var/lib/silicium/playwright-chromium-deps"
  if [[ ! -f "$deps_marker" ]] && command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    audio_package="libasound2"
    if apt-cache show libasound2t64 >/dev/null 2>&1; then
      audio_package="libasound2t64"
    fi
    apt-get update
    apt-get install -y --no-install-recommends \
      ca-certificates fonts-liberation "$audio_package" libatk-bridge2.0-0 \
      libatk1.0-0 libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 \
      libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libx11-6 \
      libx11-xcb1 libxcb1 libxcomposite1 libxdamage1 libxext6 \
      libxfixes3 libxkbcommon0 libxrandr2 libxshmfence1
    install -d -m 0755 "$(dirname "$deps_marker")"
    touch "$deps_marker"
    apt-get clean
    rm -rf /var/lib/apt/lists/*
  fi

  linux_build_deps_marker="/var/lib/silicium/linux-desktop-build-deps-v3"
  if [[ ! -f "$linux_build_deps_marker" ]] && command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    fuse_package="libfuse2"
    if apt-cache show libfuse2t64 >/dev/null 2>&1; then
      fuse_package="libfuse2t64"
    fi
    apt-get install -y --no-install-recommends \
      build-essential curl file libayatana-appindicator3-dev "$fuse_package" \
      librsvg2-dev libssl-dev libwebkit2gtk-4.1-dev patchelf python3-pip rpm
    install -d -m 0755 "$(dirname "$linux_build_deps_marker")"
    touch "$linux_build_deps_marker"
    apt-get clean
    rm -rf /var/lib/apt/lists/*
  fi
}

configure_runner_runtime

# A previous Docker build may have created root-owned files in the shared
# runner worktree. GitHub's checkout action must be able to clean that tree.
if [[ -d "$RUNNER_ROOT/_work" ]]; then
  chown -R "$RUNNER_USER":"$RUNNER_USER" "$RUNNER_ROOT/_work"
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

ensure_runner() {
  local repo="$1"
  local runner_dir="$2"
  local runner_name="$3"
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
    return 1
  fi
}

for repo in "${REPOS[@]}"; do
  slug="$(printf '%s' "$repo" | tr '[:upper:]' '[:lower:]')"
  ensure_runner \
    "$repo" \
    "${RUNNER_ROOT}-${slug}" \
    "fusion-vps-${slug}"
done

if [[ "$EXTRA_RUNNER_COUNT" =~ ^[0-9]+$ ]]; then
  if (( EXTRA_RUNNER_COUNT > 0 )); then
    for repo in Fusion Network; do
      slug="$(printf '%s' "$repo" | tr '[:upper:]' '[:lower:]')"
      for index in $(seq 1 "$EXTRA_RUNNER_COUNT"); do
        runner_dir="${RUNNER_ROOT}-${slug}-extra-${index}"
        runner_name="fusion-vps-${slug}-extra-${index}"
        if ! ensure_runner "$repo" "$runner_dir" "$runner_name"; then
          echo "Warning: optional extra runner $runner_name could not be configured." >&2
        fi
      done
    done
  fi
else
  echo "Ignoring invalid SILICIUM_EXTRA_RUNNER_COUNT=$EXTRA_RUNNER_COUNT; expected a non-negative integer." >&2
fi

unset BOOTSTRAP_TOKEN
echo "Required submodule and optional extra self-hosted runners are configured on this VPS."
