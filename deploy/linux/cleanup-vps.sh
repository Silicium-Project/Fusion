#!/usr/bin/env bash
set -euo pipefail

STALE_JOB_DAYS="${SILICIUM_STALE_JOB_DAYS:-7}"
MIN_FREE_KB="${SILICIUM_MIN_FREE_KB:-16777216}"
PRUNE_DOCKER="${SILICIUM_PRUNE_DOCKER:-auto}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/linux/cleanup-vps.sh" >&2
  exit 1
fi
[[ "$STALE_JOB_DAYS" =~ ^[0-9]+$ ]] || { echo "Invalid SILICIUM_STALE_JOB_DAYS: $STALE_JOB_DAYS" >&2; exit 1; }

if pgrep -af 'raytracer|run_network_job' >/dev/null 2>&1; then
  echo "A raytracer workload is active; refusing to clean job data." >&2
  pgrep -af 'raytracer|run_network_job' >&2 || true
  exit 2
fi

removed_jobs=0
for jobs_root in \
  /opt/silicium/Network/.silicium/jobs/raytracer \
  /opt/silicium-dev/Network/.silicium/jobs/raytracer; do
  [[ -d "$jobs_root" ]] || continue
  while IFS= read -r -d '' job_dir; do
    rm -rf -- "$job_dir"
    removed_jobs=$((removed_jobs + 1))
  done < <(find "$jobs_root" -mindepth 1 -maxdepth 1 -type d -mtime "+$STALE_JOB_DAYS" -print0)
done

removed_temp=0
for temp_root in /home/*/_work/_temp /opt/github-runner*/_work/_temp; do
  [[ -d "$temp_root" ]] || continue
  while IFS= read -r -d '' temp_dir; do
    rm -rf -- "$temp_dir"
    removed_temp=$((removed_temp + 1))
  done < <(
    find "$temp_root" -mindepth 1 -maxdepth 1 -type d \
      \( -name 'silicium-e2e-*' -o -name 'silicium-raytracer-cache' \) \
      -mmin +180 -print0
  )
done

while IFS= read -r -d '' staging_dir; do
  rm -rf -- "$staging_dir"
done < <(find /tmp -maxdepth 1 -type d -name 'silicium-release-*' -mmin +180 -print0 2>/dev/null)

free_kb="$(df -Pk / | awk 'NR == 2 {print $4}')"
if [[ "$PRUNE_DOCKER" == "1" || ( "$PRUNE_DOCKER" == "auto" && "$free_kb" -lt "$MIN_FREE_KB" ) ]]; then
  if command -v docker >/dev/null 2>&1; then
    echo "Low disk space (${free_kb} KiB free); pruning Docker build cache and unused images."
    docker builder prune -af --filter 'until=24h'
    docker image prune -af --filter 'until=168h'
    docker container prune -f
    docker network prune -f
  fi
else
  echo "Docker cache retained (${free_kb} KiB free)."
fi

if command -v apt-get >/dev/null 2>&1; then
  apt-get clean
fi
if command -v journalctl >/dev/null 2>&1; then
  journalctl --vacuum-time=14d >/dev/null || true
fi

echo "VPS cleanup complete: removed $removed_jobs stale raytracer job directories and $removed_temp temporary test directories."
df -h / /opt 2>/dev/null || df -h /
