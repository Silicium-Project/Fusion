#!/usr/bin/env python3
"""Run a real multi-container Silicium network load test.

The harness starts one world scheduler, one MCP ingress, and N worker
containers. Workers use the production pull/claim, signed peer HTTP, gossip,
and result-return paths. It intentionally does not use ``e2e_worker.py``:
that helper is a deterministic queue fixture, not a capacity test.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "dead_lettered", "cancelled", "canceled", "expired", "finalized", "resolved"}
)
DEFAULT_BATCH_SIZE = 4
MAX_WORKERS = 512
MAX_TASKS = 10_000

# Keep a heterogeneous node population in the load profile.  The scheduler
# remains a broker with storage/audit/resource capabilities, while workers
# advertise combinations that occur in the real network.  Compute and verify
# are the executable roles used by the synthetic workload; the other roles
# still participate in identity, gossip, peer-book and liveness pressure.
ROLE_PROFILES: tuple[tuple[str, ...], ...] = (
    ("compute",),
    ("compute", "verify"),
    ("verify",),
    ("storage",),
    ("audit",),
    ("resource",),
    ("compute", "storage"),
    ("verify", "audit"),
    ("storage", "resource"),
    ("compute", "verify", "resource"),
)


def worker_roles_for_index(index: int) -> str:
    """Return a deterministic heterogeneous role profile for a worker."""
    profile = ROLE_PROFILES[int(index) % len(ROLE_PROFILES)]
    return ",".join(profile)


def role_profile_counts(worker_count: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for index in range(max(0, int(worker_count))):
        for role in ROLE_PROFILES[index % len(ROLE_PROFILES)]:
            counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items()))


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value).strip()) or "item"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _node_paths(state_dir: Path, node_id: str) -> tuple[str, str, str]:
    safe_node = safe_id(node_id)
    return (
        f"/state/{safe_node}/export",
        f"/state/{safe_node}/state",
        f"/state/{safe_node}/identity.pem",
    )


def _node_command(
    *,
    node_id: str,
    roles: str,
    export_dir: str,
    state_path: str,
    identity_path: str,
    mesh_key: str,
    scheduler: bool,
    batch_size: int,
    http_workers: int = 16,
) -> list[str]:
    command = [
        "python3",
        "/workspace/tools/network_node.py",
        "--export-dir",
        export_dir,
        "--state-dir",
        state_path,
        "--identity-key-path",
        identity_path,
        "--node-id",
        node_id,
        "--roles",
        roles,
        # Match the production default.  A 25 ms sweep is useful for a tiny
        # fixture but creates a busy-loop storm when hundreds of idle workers
        # are alive and masks scheduler capacity with local CPU contention.
        "--idle-ms",
        "250",
        "--max-retries",
        "1",
        "--gossip-enable",
        "--gossip-bind",
        "0.0.0.0",
        "--gossip-port",
        "46000",
        "--gossip-advertise-host",
        node_id,
        "--gossip-advertise-port",
        "46000",
        "--peer-http-bind",
        "0.0.0.0",
        "--peer-http-port",
        "46001",
        "--peer-http-max-workers",
        str(max(1, min(256, int(http_workers)))),
        "--peer-advertise-host",
        node_id,
        "--peer-advertise-port",
        "46001",
        "--mesh-key",
        mesh_key,
        "--peer-sync-interval-s",
        "10",
        "--peer-sync-fanout",
        "8",
        "--peer-event-limit",
        "64",
        "--peer-stale-after-s",
        "120",
        "--p2p-direct-transport-backend",
        "native-light",
        "--reputation-score",
        "50",
    ]
    if scheduler:
        command.extend(["--world", "--world-name", "load-test", "--world-seeds", ""])
    else:
        command.extend(
            [
                "--seed-peers",
                "http://scheduler:46001",
                "--pull-tasks-enable",
                "--pull-tasks-interval-s",
                "1.0",
                "--pull-tasks-batch-size",
                str(batch_size),
            ]
        )
    return command


def build_compose_config(
    *,
    repo_root: Path,
    state_dir: Path,
    worker_count: int,
    batch_size: int,
    image: str = "silicium-load-test:local",
    mesh_key: str = "load-test-mesh",
    scheduler_port: int = 0,
    mcp_port: int = 0,
) -> dict[str, Any]:
    """Build a Compose document without starting Docker.

    Keeping this pure makes the topology reviewable and lets CI validate that
    every worker is a separate service with a unique identity.
    """
    worker_count = max(1, min(MAX_WORKERS, int(worker_count)))
    batch_size = max(1, min(32, int(batch_size)))
    scheduler_port = scheduler_port or _free_port()
    mcp_port = mcp_port or _free_port()
    # ``Z`` keeps the bind mounts readable under rootless Podman/SELinux while
    # remaining a no-op on Docker hosts without SELinux labeling.
    repo_mount = f"{repo_root.resolve().as_posix()}:/workspace:ro,Z"
    state_mount = f"{state_dir.resolve().as_posix()}:/state:Z"

    scheduler_export, scheduler_state, scheduler_identity = _node_paths(state_dir, "scheduler")
    services: dict[str, Any] = {
        "scheduler": {
            "image": image,
            "build": {"context": repo_root.resolve().as_posix(), "dockerfile": "infra/docker/load-test.Dockerfile"},
            "command": _node_command(
                node_id="scheduler",
                # Keep the world node as a broker during the benchmark so the
                # measured completions come from the isolated worker pool.
                roles="storage,audit,resource",
                export_dir=scheduler_export,
                state_path=scheduler_state,
                identity_path=scheduler_identity,
                mesh_key=mesh_key,
                scheduler=True,
                batch_size=batch_size,
                http_workers=64,
            ),
            "environment": {"PYTHONPATH": "/workspace", "SILICIUM_SOLANA_ENABLE": "0"},
            "security_opt": ["label=disable"],
            "volumes": [repo_mount, state_mount],
            "ports": [f"127.0.0.1:{scheduler_port}:46001"],
            "restart": "on-failure",
        },
        "mcp": {
            "image": image,
            "command": [
                "python3",
                "/workspace/tools/mcp_server.py",
                "--bind",
                "0.0.0.0",
                "--port",
                "9765",
                "--export-dir",
                scheduler_export,
                "--enable-tools",
                "--no-auth",
            ],
            "environment": {"PYTHONPATH": "/workspace"},
            "security_opt": ["label=disable"],
            "volumes": [repo_mount, state_mount],
            "ports": [f"127.0.0.1:{mcp_port}:9765"],
            "depends_on": ["scheduler"],
        },
    }

    for index in range(worker_count):
        node_id = f"worker-{index + 1:03d}"
        service_name = node_id
        export_dir, state_path, identity_path = _node_paths(state_dir, node_id)
        roles = worker_roles_for_index(index)
        services[service_name] = {
            "image": image,
            "command": _node_command(
                node_id=node_id,
                roles=roles,
                export_dir=export_dir,
                state_path=state_path,
                identity_path=identity_path,
                mesh_key=mesh_key,
                scheduler=False,
                batch_size=batch_size,
                http_workers=8,
            ),
            "environment": {"PYTHONPATH": "/workspace", "SILICIUM_SOLANA_ENABLE": "0"},
            "security_opt": ["label=disable"],
            "volumes": [repo_mount, state_mount],
            "depends_on": ["scheduler"],
            "restart": "on-failure",
        }

    return {
        "services": services,
        "networks": {"default": {"name": f"silicium-load-{safe_id(mesh_key)}"}},
    }


def build_task(index: int, *, verify: bool = False) -> dict[str, Any]:
    """Create a small but non-empty task for the built-in runtime."""
    task_id = f"load-{('verify' if verify else 'compute')}-{index:06d}"
    payload = {"sequence": index, "payload": f"silicium-load-payload-{index:06d}"}
    task: dict[str, Any] = {
        "kind": "verify" if verify else "compute",
        "workload": "verification/hash-audit/sha256" if verify else "calcul/integrity/sha256",
        "inline_input": payload,
        "timeout_s": 30,
    }
    if verify:
        raw = stable_json(payload).encode("utf-8")
        task["expected_hash"] = hashlib.sha256(raw).hexdigest()
    return {
        "task_id": task_id,
        "task": task,
        "required_roles": ["verify"] if verify else ["compute"],
        "priority": "normal",
    }


def _http_json(url: str, *, method: str = "GET", payload: Any | None = None, timeout: float = 5.0) -> Any:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = stable_json(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_http(url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + max(1.0, timeout_s)
    last_error = ""
    while time.monotonic() < deadline:
        try:
            payload = _http_json(url, timeout=2.0)
            if isinstance(payload, dict) and payload.get("ok") is True:
                return
            last_error = f"unexpected_health:{payload!r}"
        except Exception as exc:  # startup races are expected
            last_error = f"{type(exc).__name__}:{exc}"
        time.sleep(0.25)
    raise RuntimeError(f"service_not_ready:{url}:{last_error}")


def _resolve_compose_prefix(configured: str = "") -> list[str]:
    if configured.strip():
        prefix = shlex.split(configured)
        if not prefix:
            raise RuntimeError("compose_command_empty")
        return prefix
    candidates = (["docker", "compose"], ["docker-compose"], ["podman", "compose"], ["podman-compose"])
    for candidate in candidates:
        if not shutil.which(candidate[0]):
            continue
        try:
            probe = subprocess.run(
                [*candidate, "version"],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            return list(candidate)
    raise RuntimeError("compose_runtime_not_found: install Docker Compose or set --compose-command")


def _compose_command(compose_prefix: list[str], compose_file: Path, project_name: str, *args: str) -> list[str]:
    return [*compose_prefix, "--project-name", project_name, "--file", str(compose_file), *args]


def _run_compose(
    compose_prefix: list[str],
    compose_file: Path,
    project_name: str,
    args: list[str],
    *,
    timeout_s: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _compose_command(compose_prefix, compose_file, project_name, *args),
        text=True,
        capture_output=True,
        timeout=max(30.0, timeout_s),
        check=False,
    )


def _run_compose_checked(
    compose_prefix: list[str],
    compose_file: Path,
    project_name: str,
    args: list[str],
    *,
    timeout_s: float,
    phase: str,
) -> subprocess.CompletedProcess[str]:
    completed = _run_compose(
        compose_prefix,
        compose_file,
        project_name,
        args,
        timeout_s=timeout_s,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "compose returned a non-zero status")[-4000:]
        raise RuntimeError(f"{phase}_failed:{detail}")
    return completed


def _start_compose_services(
    compose_prefix: list[str],
    compose_file: Path,
    project_name: str,
    *,
    worker_ids: list[str],
    scheduler_port: int,
    startup_timeout_s: float,
    compose_timeout_s: float,
    no_build: bool,
    start_batch_size: int,
    start_delay_s: float,
) -> None:
    """Build once and start the topology in bounded waves.

    Starting hundreds of Python containers in one Compose transaction creates
    an avoidable CPU/RAM thundering herd on small qualification hosts. The
    scheduler is made healthy first, then the MCP ingress and workers are
    started in bounded batches so the test measures the network rather than
    the container runtime's startup burst.
    """
    if not no_build:
        _run_compose_checked(
            compose_prefix,
            compose_file,
            project_name,
            ["build"],
            timeout_s=compose_timeout_s,
            phase="compose_build",
        )

    _run_compose_checked(
        compose_prefix,
        compose_file,
        project_name,
        ["up", "-d", "scheduler"],
        timeout_s=compose_timeout_s,
        phase="scheduler_start",
    )
    _wait_http(f"http://127.0.0.1:{scheduler_port}/health", startup_timeout_s)

    _run_compose_checked(
        compose_prefix,
        compose_file,
        project_name,
        ["up", "-d", "mcp"],
        timeout_s=compose_timeout_s,
        phase="mcp_start",
    )
    batch_size = max(1, int(start_batch_size))
    for offset in range(0, len(worker_ids), batch_size):
        batch = worker_ids[offset : offset + batch_size]
        _run_compose_checked(
            compose_prefix,
            compose_file,
            project_name,
            ["up", "-d", *batch],
            timeout_s=compose_timeout_s,
            phase=f"worker_start_{offset + 1}_{offset + len(batch)}",
        )
        if start_delay_s > 0 and offset + len(batch) < len(worker_ids):
            time.sleep(float(start_delay_s))


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _task_path(state_dir: Path, task_id: str) -> Path:
    return state_dir / "scheduler" / "export" / "tasks" / f"{safe_id(task_id)}.json"


def _poll_tasks(
    state_dir: Path,
    task_ids: list[str],
    submitted_at: dict[str, float],
    timeout_s: float,
) -> tuple[dict[str, dict[str, Any]], list[float]]:
    deadline = time.monotonic() + max(1.0, timeout_s)
    final: dict[str, dict[str, Any]] = {}
    latencies: list[float] = []
    while task_ids and time.monotonic() < deadline:
        for task_id in task_ids:
            if task_id in final:
                continue
            envelope = _read_json(_task_path(state_dir, task_id), {})
            if not isinstance(envelope, dict):
                continue
            status = str(envelope.get("status", "")).lower()
            if status in TERMINAL_STATUSES:
                final[task_id] = envelope
                start = submitted_at.get(task_id)
                if start is not None:
                    latencies.append(max(0.0, time.monotonic() - start))
        if len(final) == len(task_ids):
            break
        time.sleep(0.2)
    for task_id in task_ids:
        if task_id not in final:
            final[task_id] = _read_json(_task_path(state_dir, task_id), {"task_id": task_id, "status": "timeout"})
    return final, latencies


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = min(len(ordered) - 1, max(0, int(round((percentile / 100.0) * (len(ordered) - 1)))))
    return round(ordered[position], 6)


def _collect_runtime(state_dir: Path, worker_ids: list[str]) -> dict[str, Any]:
    workers: dict[str, Any] = {}
    for node_id in ["scheduler", *worker_ids]:
        export_dir = state_dir / safe_id(node_id) / "export"
        prefix = f"node.{safe_id(node_id)}"
        workers[node_id] = {
            "heartbeat": _read_json(export_dir / f"{prefix}.heartbeat.json", {}),
            "metrics": _read_json(export_dir / f"{prefix}.metrics.json", {}),
            "claim_poll": _read_json(export_dir / "claim-poll.health.json", {}),
        }
    peers = _read_json(state_dir / "scheduler" / "export" / "node.scheduler.peers.json", {})
    return {"nodes": workers, "scheduler_peers": peers if isinstance(peers, dict) else {}}


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_load_test(args: argparse.Namespace) -> dict[str, Any]:
    worker_count = max(1, min(MAX_WORKERS, int(args.workers)))
    task_count = max(1, min(MAX_TASKS, int(args.tasks)))
    batch_size = max(1, min(32, int(args.batch_size)))
    compose_prefix = _resolve_compose_prefix(str(args.compose_command))

    repo_root = Path(__file__).resolve().parents[1]
    report_path = Path(args.report).expanduser().resolve() if args.report else repo_root / ".silicium" / "load-tests" / f"load-{int(time.time())}.json"
    project_name = safe_id(args.project_name or f"silicium-load-{int(time.time())}-{uuid.uuid4().hex[:6]}")[:50]
    state_dir = Path(tempfile.mkdtemp(prefix="silicium-load-"))
    compose_file = state_dir / "compose.json"
    scheduler_port = _free_port()
    mcp_port = _free_port()
    config = build_compose_config(
        repo_root=repo_root,
        state_dir=state_dir,
        worker_count=worker_count,
        batch_size=batch_size,
        image=str(args.image),
        mesh_key=project_name,
        scheduler_port=scheduler_port,
        mcp_port=mcp_port,
    )
    compose_file.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    worker_ids = [f"worker-{index + 1:03d}" for index in range(worker_count)]
    task_specs = [build_task(index, verify=(index % 5 == 0)) for index in range(task_count)]
    mcp_url = f"http://127.0.0.1:{mcp_port}"
    started_monotonic = time.monotonic()
    started_unix = time.time()
    submitted_at: dict[str, float] = {}
    submissions: dict[str, Any] = {}
    final: dict[str, dict[str, Any]] = {}
    compose_error = ""
    try:
        _start_compose_services(
            compose_prefix,
            compose_file,
            project_name,
            worker_ids=worker_ids,
            scheduler_port=scheduler_port,
            startup_timeout_s=float(args.startup_timeout_s),
            compose_timeout_s=float(args.compose_timeout_s),
            no_build=bool(args.no_build),
            start_batch_size=int(args.start_batch_size),
            start_delay_s=float(args.start_delay_s),
        )
        _wait_http(mcp_url + "/healthz", float(args.startup_timeout_s))

        def submit(spec: dict[str, Any]) -> tuple[str, Any, float]:
            task_id = str(spec["task_id"])
            submitted = time.monotonic()
            response = _http_json(mcp_url + "/tasks", method="POST", payload=spec, timeout=10.0)
            return task_id, response, submitted

        with ThreadPoolExecutor(max_workers=min(64, task_count)) as executor:
            futures = [executor.submit(submit, spec) for spec in task_specs]
            for future in as_completed(futures):
                task_id, response, submitted = future.result()
                submissions[task_id] = response
                submitted_at[task_id] = submitted

        final, latencies = _poll_tasks(state_dir, [str(item["task_id"]) for item in task_specs], submitted_at, float(args.timeout_s))
        elapsed_s = max(0.001, time.monotonic() - started_monotonic)
        completed = [item for item in final.values() if str(item.get("status", "")).lower() == "completed"]
        failed = [item for item in final.values() if str(item.get("status", "")).lower() not in {"completed"}]
        distribution: dict[str, int] = {}
        for item in final.values():
            worker = str(item.get("handled_by", "unknown")) or "unknown"
            distribution[worker] = distribution.get(worker, 0) + 1
        report = {
            "schema_version": 1,
            "test": "real-p2p-multi-instance",
            "started_unix": started_unix,
            "duration_s": round(elapsed_s, 6),
            "topology": {
                "workers_requested": worker_count,
                "tasks_requested": task_count,
                "batch_size": batch_size,
                "worker_role_counts": role_profile_counts(worker_count),
                "scheduler_host_port": scheduler_port,
                "mcp_host_port": mcp_port,
                "containers_are_isolated_instances": True,
                "compose_command": " ".join(compose_prefix),
            },
            "submission": {
                "submitted": len(submissions),
                "submission_errors": task_count - len(submissions),
            },
            "results": {
                "completed": len(completed),
                "failed_or_timeout": len(failed),
                "throughput_tasks_per_second": round(len(completed) / elapsed_s, 6),
                "latency_seconds": {
                    "p50": _percentile(latencies, 50),
                    "p95": _percentile(latencies, 95),
                    "max": round(max(latencies), 6) if latencies else 0.0,
                },
                "handled_by": distribution,
                "failed_task_ids": sorted(str(item.get("task_id", "")) for item in failed)[:100],
            },
            "runtime": _collect_runtime(state_dir, worker_ids),
            "tasks": final,
            "submissions": submissions,
            "compose_file": str(compose_file) if args.keep else "",
            "report_path": str(report_path),
        }
        _write_report(report_path, report)
        if failed and not args.allow_failures:
            raise RuntimeError(f"load_test_failures:{len(failed)}:{report_path}")
        return report
    finally:
        if not args.keep:
            down = _run_compose(
                compose_prefix,
                compose_file,
                project_name,
                ["down", "--remove-orphans"],
                timeout_s=120,
            )
            if down.returncode != 0 and not compose_error:
                compose_error = (down.stderr or down.stdout)[-2000:]
            shutil.rmtree(state_dir, ignore_errors=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="load_test", description=__doc__)
    parser.add_argument("--workers", type=int, default=32, help="Number of isolated worker containers (default: 32).")
    parser.add_argument("--tasks", type=int, default=256, help="Number of tasks submitted to MCP (default: 256).")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Tasks reserved per signed claim request.")
    parser.add_argument("--timeout-s", type=float, default=300.0, help="Result convergence timeout.")
    parser.add_argument("--startup-timeout-s", type=float, default=90.0, help="MCP startup timeout.")
    parser.add_argument("--compose-timeout-s", type=float, default=600.0, help="Docker build/start timeout.")
    parser.add_argument(
        "--start-batch-size",
        type=int,
        default=8,
        help="Workers to start per Compose wave (default: 8; lower this on small hosts).",
    )
    parser.add_argument(
        "--start-delay-s",
        type=float,
        default=0.1,
        help="Delay between worker startup waves (default: 0.1).",
    )
    parser.add_argument("--report", default="", help="JSON report path.")
    parser.add_argument("--project-name", default="", help="Docker Compose project name.")
    parser.add_argument("--compose-command", default="", help="Compose executable, e.g. 'docker compose' or 'podman-compose'.")
    parser.add_argument("--image", default="silicium-load-test:local", help="Worker/scheduler image tag.")
    parser.add_argument("--no-build", action="store_true", help="Use an already-built image.")
    parser.add_argument("--keep", action="store_true", help="Keep the Compose project and temporary state after the run.")
    parser.add_argument("--allow-failures", action="store_true", help="Write the report and return success despite failed tasks.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        report = run_load_test(args)
    except Exception as exc:
        print(f"load test failed: {type(exc).__name__}: {exc}")
        return 1
    print(json.dumps({
        "report": report["report_path"],
        "workers": report["topology"]["workers_requested"],
        "tasks": report["topology"]["tasks_requested"],
        "completed": report["results"]["completed"],
        "throughput_tasks_per_second": report["results"]["throughput_tasks_per_second"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
