import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = REPO_ROOT / "infra" / "docker" / "solana-entrypoint.sh"
COMMANDS_TO_STUB = [
    "solana",
    "solana-keygen",
    "solana-test-validator",
    "solana-validator",
    "getent",
]


def _write_stub(script_path: Path, command_name: str) -> None:
    script_path.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
cmd="{command_name}"
: "${{STUB_LOG_DIR:?Need STUB_LOG_DIR}}"
log_file="${{STUB_LOG_DIR}}/{command_name}.log"
mkdir -p "$(dirname "$log_file")"
printf '%s\\n' "$cmd $*" >> "$log_file"
case "$cmd" in
  solana-keygen)
    outfile=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --outfile)
          outfile="$2"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    if [[ -n "$outfile" ]]; then
      mkdir -p "$(dirname "$outfile")"
      echo 'stub-keypair' > "$outfile"
    fi
    ;;
  solana)
    if [[ "${{1:-}}" == "balance" ]]; then
      echo "0 SOL"
    fi
    ;;
  getent)
    if [[ "${{1:-}}" == "hosts" && -n "${{2:-}}" ]]; then
      echo "127.0.0.1 $2"
    fi
    ;;
esac
exit 0
"""
    )
    script_path.chmod(0o755)


def _init_stub_bin(root: Path) -> Path:
    bin_dir = root / "stub-bin"
    bin_dir.mkdir()
    for cmd in COMMANDS_TO_STUB:
        _write_stub(bin_dir / cmd, cmd)
    return bin_dir


def _read_log_lines(log_dir: Path, command: str) -> list[str]:
    log_file = log_dir / f"{command}.log"
    if not log_file.exists():
        return []
    return [
        line.strip()
        for line in log_file.read_text().splitlines()
        if line.strip()
    ]


@pytest.fixture
def entrypoint_runner(tmp_path_factory):
    root = tmp_path_factory.mktemp("silicium-tests")
    stub_bin = _init_stub_bin(root)
    logs_dir = root / "logs"
    logs_dir.mkdir()
    home_dir = root / "home"
    base_env = {
        "PATH": f"{stub_bin}:{os.environ.get('PATH', '')}",
        "HOME": str(home_dir),
        "STUB_LOG_DIR": str(logs_dir),
        "SILICIUM_LOCAL_RESET": "false",
    }

    def _run(args: list[str], *, extra_env: dict | None = None):
        env = os.environ.copy()
        env.update(base_env)
        if extra_env:
            env.update(extra_env)

        result = subprocess.run(
            ["bash", str(ENTRYPOINT), *args],
            capture_output=True,
            text=True,
            env=env,
        )
        return SimpleNamespace(
            result=result,
            logs=logs_dir,
            home=home_dir,
            read_log=lambda name: _read_log_lines(logs_dir, name),
        )

    return _run
