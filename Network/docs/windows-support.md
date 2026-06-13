# Windows Support Matrix

This document describes what is supported on Windows today, by runtime mode.
It is intentionally explicit about what is tested in CI vs best-effort.

Terminology
- "Windows native": running commands in PowerShell / cmd.exe (no WSL shell).
- "Docker Desktop": Docker Desktop installed and the Windows `docker.exe` works.
- "WSL": running inside a Linux distribution (e.g. Ubuntu on WSL2).

## Recommended Setup (Windows)

1. Install Python (3.11+ recommended).
2. Install OpenSSL (required by the signed P2P node identity).
3. Install Docker Desktop (recommended for core checks and infra).
4. Optional: install WSL2 + one distro (Ubuntu) if you want to run bash scripts directly.

## One-command launcher

From the repository root on Windows:

```powershell
.\start-silicium-windows.cmd
```

The launcher checks Python, Node.js, npm, OpenSSL and Docker, installs Python and
dashboard dependencies, starts the read-only Devnet dashboard, and starts the
Docker world node when Docker is available.

Useful options:

```powershell
.\start-silicium-windows.cmd -SkipInstall
.\start-silicium-windows.cmd -InstallSystemDeps
.\start-silicium-windows.cmd -SkipWorldNode
.\start-silicium-windows.cmd -NoBrowser
.\start-silicium-windows.cmd -RunDoctor
.\start-silicium-windows.cmd -NodeId croatia-1 -WorldSeeds http://100.112.48.71:46001
```

`-InstallSystemDeps` uses `winget` to install missing system tools when possible
(Python, Node.js LTS, OpenSSL Light, Docker Desktop). Reopen PowerShell after
system installs if Windows does not refresh `PATH` immediately.

OpenSSL is required by `silicium node start` to create and use the local peer
identity. Without it, the render3d full demo can still run in `--node-mode auto`
through its inline fallback, but `--node-mode cli` will fail before the signed
P2P node starts.

## Modes

### Mode A: Windows native + Docker Desktop (Recommended)

What you can do:
- `python .\\silicium test`
- `python .\\silicium test --entrypoint-docker` (exécute `tests/test_entrypoint.py` dans un conteneur Linux)
- `python .\\silicium tui` (Textual when available, else headless shell fallback)
- `python .\\silicium check --runner docker` (core checks in container)
- `python .\\silicium smoke` (proxy smoke, requires Docker)

What you typically cannot do without WSL:
- Running `ci/*.sh` and `infra/**/*.sh` directly (bash scripts).

### Mode B: Windows native (No Docker, No WSL)

What you can do:
- `python .\\silicium workload lint` (manifest validation only)
- `python .\\silicium test` (Python-only tests; some infra paths are skipped on Windows)

Constraints:
- No Docker-backed checks (`silicium check --full`, DynamoRIO, proxy smoke).
- No direct execution of bash scripts.

### Mode C: WSL (Ubuntu) + Docker Desktop integration

What you can do:
- Run bash scripts directly (e.g. `ci/e2e.sh`, `infra/bin/run-with-proxy.sh`).
- Run Linux toolchain-dependent builds (`make`, `g++`, binutils).

Constraints:
- Requires Docker Desktop -> WSL Integration enabled for the distro.
- File path interop: prefer running in the same environment consistently (all-in-WSL or all-in-Windows).

## Support Matrix

Legend: "CI" = validated in GitHub Actions, "Local" = works but not CI-gated.

| Capability | Windows native | Win + Docker Desktop | WSL + Docker Desktop |
|---|---:|---:|---:|
| `python .\\silicium test` | CI | CI | Local |
| `python .\\silicium test --entrypoint-docker` | - | Local | Local |
| `python .\\silicium tui` | Local | Local | Local |
| `python .\\silicium check --runner docker` | - | Local | Local |
| `python .\\silicium check --runner wsl` | - | - | Local |
| `python .\\silicium smoke` | - | Local | Local |
| Run `ci/*.sh` directly | - | - | Local |
| Run `infra/**/*.sh` directly | - | - | Local |

## Diagnostics

Use:
- `python .\\silicium doctor`

Expected signals:
- Docker: OK/FAIL with a short reason.
- On Windows, WSL distro listing and Docker socket integration hints.

For C++ test runs (`python .\\silicium cpp-test`):
- The CLI now checks Docker memory and fails fast if too low.
- Default minimum is 2048 MB (override with `SILICIUM_CPP_TEST_MIN_DOCKER_MEMORY_MB`, set `0` to disable).
