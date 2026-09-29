"""Docker, Docker Compose and WSL helpers: health probes, diagnostics and
compose up/stop/down for the local services.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tools.cli.constants import COMPOSE_ENV_FILE, COMPOSE_FILE, SERVICE_MAP
from tools.cli.context import Context, DockerHealth
from tools.cli.framework import _emit_cli_event
from tools.cli.proc import COLOR_YELLOW, colorize, run, run_capture


def _classify_docker_probe_failure(output: str) -> tuple[str, str]:
    text = output.lower()
    if "unexpected eof" in text or "_ping" in text or "internal server error" in text:
        return ("docker_api_error", "Docker API unreachable (transient daemon/API error).")
    if "is the docker daemon running" in text:
        return ("docker_daemon_unavailable", "Docker daemon is not running.")
    if "cannot connect to the docker daemon" in text:
        return ("docker_daemon_unavailable", "Cannot connect to Docker daemon.")
    if "permission denied" in text:
        return ("docker_permission_denied", "Permission denied while accessing Docker daemon.")
    return ("docker_probe_failed", "Docker health probe failed.")


def docker_memory_bytes(ctx: Context, *, timeout_s: float = 8.0) -> int | None:
    try:
        result = subprocess.run(
            [ctx.config.docker_bin, "info", "--format", "{{.MemTotal}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    raw = (result.stdout or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def docker_health(ctx: Context, retries: int = 0, timeout_s: float = 8.0) -> DockerHealth:
    if not shutil.which(ctx.config.docker_bin):
        return DockerHealth(
            ok=False,
            error_code="docker_not_installed",
            message=f"Docker binary '{ctx.config.docker_bin}' not found in PATH.",
        )

    attempt = 0
    max_attempts = max(1, retries + 1)
    last_health = DockerHealth(False, "docker_probe_failed", "Docker health probe failed.")
    while attempt < max_attempts:
        attempt += 1
        try:
            result = subprocess.run(
                [ctx.config.docker_bin, "info", "--format", "{{.ServerVersion}}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            if result.returncode == 0:
                return DockerHealth(ok=True, error_code="", message="ok", detail=result.stdout.strip())

            combined = (result.stdout or "") + "\n" + (result.stderr or "")
            code, msg = _classify_docker_probe_failure(combined)
            last_health = DockerHealth(ok=False, error_code=code, message=msg, detail=combined.strip())
        except subprocess.TimeoutExpired as exc:
            last_health = DockerHealth(
                ok=False,
                error_code="docker_probe_timeout",
                message="Docker health probe timed out.",
                detail=str(exc),
            )
        except OSError as exc:
            last_health = DockerHealth(
                ok=False,
                error_code="docker_launch_error",
                message="Failed to launch Docker binary.",
                detail=str(exc),
            )

        if last_health.error_code not in {"docker_api_error", "docker_probe_timeout"}:
            break
        if attempt < max_attempts:
            time.sleep(0.75 * attempt)

    return last_health


def print_docker_diagnostics(ctx: Context, health: DockerHealth) -> None:
    docker_host = os.environ.get("DOCKER_HOST", "<unset>")
    print(f"Docker check failed: [{health.error_code}] {health.message}")
    print(f"docker_bin={ctx.config.docker_bin} os={host_os_name()} DOCKER_HOST={docker_host}")
    if health.detail:
        detail = health.detail.strip().replace("\n", " | ")
        print(f"detail={detail[:800]}")
    if health.error_code == "docker_not_installed":
        print("Install Docker Desktop (Windows/macOS) or Docker Engine (Linux) and retry.")
    elif health.error_code in {"docker_daemon_unavailable", "docker_api_error", "docker_probe_timeout"}:
        print("Start/restart Docker Desktop (or dockerd), then retry.")
    elif health.error_code == "docker_permission_denied":
        print("Fix Docker daemon permissions (docker group / elevated shell) and retry.")


def ensure_docker_healthy(
    ctx: Context,
    *,
    retries: int = 2,
    timeout_s: float = 8.0,
    min_memory_bytes: int | None = None,
) -> None:
    health = docker_health(ctx, retries=retries, timeout_s=timeout_s)
    if not health.ok:
        print_docker_diagnostics(ctx, health)
        sys.exit(1)
    if min_memory_bytes is None or min_memory_bytes <= 0:
        return
    mem_total = docker_memory_bytes(ctx, timeout_s=timeout_s)
    if mem_total is None:
        return
    if mem_total >= min_memory_bytes:
        return
    mem_gib = mem_total / float(1024 ** 3)
    min_gib = min_memory_bytes / float(1024 ** 3)
    print(
        "Docker memory too low for this command: "
        f"{mem_gib:.2f} GiB available, {min_gib:.2f} GiB required."
    )
    if host_os_name() == "nt":
        print("Windows hint: increase WSL2/Docker memory (Docker Desktop Resources or ~/.wslconfig).")
    sys.exit(1)


def host_os_name() -> str:
    return os.name


def wsl_available() -> bool:
    if host_os_name() != "nt":
        return False
    return bool(shutil.which("wsl.exe") or shutil.which("wsl"))


def list_wsl_distros() -> list[dict[str, str]]:
    if not wsl_available():
        return []
    wsl_bin = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl_bin:
        return []
    code, out, err = run_capture([wsl_bin, "-l", "-v"], timeout_s=6.0)
    if code != 0:
        detail = (out + err).strip()
        if detail:
            print(f"WSL listing failed: {detail}")
        return []
    distros: list[dict[str, str]] = []
    lines = [line.rstrip() for line in out.splitlines() if line.strip()]
    for line in lines[1:]:
        default = line.lstrip().startswith("*")
        cleaned = line.replace("*", "", 1).strip() if default else line.strip()
        parts = cleaned.split()
        if len(parts) < 3:
            continue
        version = parts[-1]
        state = parts[-2]
        name = " ".join(parts[:-2])
        distros.append(
            {
                "name": name,
                "state": state,
                "version": version,
                "default": "yes" if default else "no",
            }
        )
    return distros


def compose_command(ctx: Context) -> list[str]:
    if ctx.config.docker_compose_bin:
        return shlex.split(ctx.config.docker_compose_bin)
    if shutil.which(ctx.config.docker_bin):
        try:
            subprocess.run(
                [ctx.config.docker_bin, "compose", "version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return [ctx.config.docker_bin, "compose"]
        except subprocess.SubprocessError:
            pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    print("Docker Compose not available. Install Compose v2 or docker-compose, or set DOCKER_COMPOSE_BIN.")
    sys.exit(1)


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def confirm(prompt: str) -> bool:
    reply = input(f"{colorize(prompt, COLOR_YELLOW)} [y/N] ").strip().lower()
    return reply in {"y", "yes"}


def resolve_service(name: str) -> tuple[str, str | None]:
    if name not in SERVICE_MAP:
        print(f"Unknown service '{name}'.")
        sys.exit(1)
    return SERVICE_MAP[name]


def compose_base(ctx: Context) -> list[str]:
    ensure_docker_healthy(ctx, retries=2, timeout_s=8.0)
    base = compose_command(ctx)
    if COMPOSE_ENV_FILE.exists():
        base += ["--env-file", str(COMPOSE_ENV_FILE)]
    base += ["-f", str(COMPOSE_FILE)]
    return base


def compose_up(service: str, profile: str | None, ctx: Context, *, target: str = "") -> None:
    _emit_cli_event(
        "info",
        "dispatch_target",
        "Dispatching compose up target",
        {
            "action": "compose_up",
            "target": target or service,
            "service": service,
            "profile": profile or "",
        },
    )
    cmd = compose_base(ctx)
    if profile:
        cmd += ["--profile", profile]
    cmd += ["up", "-d", service]
    run(cmd)


def compose_stop(service: str, profile: str | None, ctx: Context, remove: bool = False, *, target: str = "") -> None:
    _emit_cli_event(
        "info",
        "dispatch_target",
        "Dispatching compose stop target",
        {
            "action": "compose_stop",
            "target": target or service,
            "service": service,
            "profile": profile or "",
            "remove": remove,
        },
    )
    cmd = compose_base(ctx)
    if profile:
        cmd += ["--profile", profile]
    cmd += ["stop", service]
    run(cmd)
    if remove:
        rm_cmd = compose_base(ctx)
        if profile:
            rm_cmd += ["--profile", profile]
        rm_cmd += ["rm", "-f", service]
        run(rm_cmd)


def compose_down(ctx: Context, volumes: bool = False) -> None:
    _emit_cli_event(
        "info",
        "dispatch_target",
        "Dispatching compose down target",
        {
            "action": "compose_down",
            "target": "all",
            "service": "all",
            "profile": "",
            "volumes": volumes,
        },
    )
    cmd = compose_base(ctx) + ["down"]
    if volumes:
        cmd.append("-v")
    run(cmd)
