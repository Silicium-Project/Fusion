from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SILICIUM_PATH = REPO_ROOT / "silicium"


def _load_silicium_module():
    module_name = "silicium_cli_test"
    loader = SourceFileLoader(module_name, str(SILICIUM_PATH))
    spec = importlib.util.spec_from_loader(module_name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


def _make_ctx(cli):
    return cli.Context(
        config=cli.EnvConfig(
            docker_bin="docker",
            docker_compose_bin=None,
            ledger_prefix="silicium",
            core_check_image="silicium/core-check:lite",
            core_check_setup=None,
            cpp_test_image="silicium/cpp-tests:latest",
        )
    )


def test_configure_test_exposes_entrypoint_docker_flags() -> None:
    cli = _load_silicium_module()
    parser = argparse.ArgumentParser()
    cli.configure_test(parser)

    args = parser.parse_args([])
    assert args.entrypoint_docker is False
    assert args.posix_pytest_image == cli.POSIX_PYTEST_IMAGE_DEFAULT

    args = parser.parse_args(["--entrypoint-docker", "--posix-pytest-image", "python:3.12-slim"])
    assert args.entrypoint_docker is True
    assert args.posix_pytest_image == "python:3.12-slim"


def test_cmd_test_entrypoint_docker_ignores_host_entrypoint(monkeypatch) -> None:
    cli = _load_silicium_module()
    calls: list[list[str]] = []
    posix_called = {"value": False}

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return 0

    def fake_workload_lint(args, ctx):
        return None

    def fake_posix(args, ctx):
        posix_called["value"] = True

    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(cli, "cmd_workload_lint", fake_workload_lint)
    monkeypatch.setattr(cli, "_run_entrypoint_posix_tests_in_docker", fake_posix)

    ctx = _make_ctx(cli)
    args = argparse.Namespace(entrypoint_docker=True, posix_pytest_image=cli.POSIX_PYTEST_IMAGE_DEFAULT)
    cli.cmd_test(args, ctx)

    assert posix_called["value"] is True
    pytest_cmds = [cmd for cmd in calls if cmd[:3] == [sys.executable, "-m", "pytest"]]
    assert len(pytest_cmds) == 1
    assert "--ignore=tests/test_entrypoint.py" in pytest_cmds[0]


def test_cmd_test_default_runs_host_pytest(monkeypatch) -> None:
    cli = _load_silicium_module()
    calls: list[list[str]] = []
    posix_called = {"value": False}

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return 0

    def fake_workload_lint(args, ctx):
        return None

    def fake_posix(args, ctx):
        posix_called["value"] = True

    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(cli, "cmd_workload_lint", fake_workload_lint)
    monkeypatch.setattr(cli, "_run_entrypoint_posix_tests_in_docker", fake_posix)

    ctx = _make_ctx(cli)
    args = argparse.Namespace(entrypoint_docker=False, posix_pytest_image=cli.POSIX_PYTEST_IMAGE_DEFAULT)
    cli.cmd_test(args, ctx)

    assert posix_called["value"] is False
    pytest_cmds = [cmd for cmd in calls if cmd[:3] == [sys.executable, "-m", "pytest"]]
    assert len(pytest_cmds) == 1
    assert pytest_cmds[0] == [sys.executable, "-m", "pytest"]


def test_cmd_check_windows_auto_uses_docker_without_wsl(monkeypatch) -> None:
    cli = _load_silicium_module()
    docker_calls: list[dict] = []
    wsl_checked = {"value": 0}

    def fake_docker_available(ctx):
        return True

    def fake_wsl_available():
        wsl_checked["value"] += 1
        return False

    def fake_ensure_docker_healthy(ctx, retries, timeout_s, min_memory_bytes=None):
        return None

    def fake_run_core_check_in_docker(env_vars, ctx):
        docker_calls.append(dict(env_vars))

    monkeypatch.setattr(cli, "host_os_name", lambda: "nt")
    monkeypatch.setattr(cli, "docker_available", fake_docker_available)
    monkeypatch.setattr(cli, "wsl_available", fake_wsl_available)
    monkeypatch.setattr(cli, "ensure_docker_healthy", fake_ensure_docker_healthy)
    monkeypatch.setattr(cli, "run_core_check_in_docker", fake_run_core_check_in_docker)

    args = argparse.Namespace(
        docker_strict=False,
        full=False,
        native=False,
        dynamo=False,
        require_docker=False,
        scope="all",
        jobs=None,
        docker_cpus="",
        docker_memory="",
        docker=None,
        clean=None,
        python="",
        runner="auto",
    )
    cli.cmd_check(args, _make_ctx(cli))

    assert len(docker_calls) == 1
    assert docker_calls[0]["CORE_CHECK_MODE"] == "quick"
    assert docker_calls[0]["CORE_CHECK_CLEAN"] == "0"
    assert docker_calls[0]["CORE_CHECK_JOBS"] == "2"
    assert wsl_checked["value"] == 0


def test_configure_check_exposes_clean_flags() -> None:
    cli = _load_silicium_module()
    parser = argparse.ArgumentParser()
    cli.configure_check(parser)

    args = parser.parse_args([])
    assert args.clean is None

    args = parser.parse_args(["--clean"])
    assert args.clean is True

    args = parser.parse_args(["--no-clean"])
    assert args.clean is False


def test_ensure_docker_healthy_fails_on_low_memory(monkeypatch, capsys) -> None:
    cli = _load_silicium_module()

    monkeypatch.setattr(cli, "docker_health", lambda ctx, retries, timeout_s: cli.DockerHealth(True, "", "ok"))
    monkeypatch.setattr(cli, "docker_memory_bytes", lambda ctx, timeout_s=8.0: 512 * 1024 * 1024)
    monkeypatch.setattr(cli, "host_os_name", lambda: "nt")

    with pytest.raises(SystemExit) as exc:
        cli.ensure_docker_healthy(_make_ctx(cli), min_memory_bytes=2 * 1024 * 1024 * 1024)

    assert int(exc.value.code) == 1
    captured = capsys.readouterr()
    assert "Docker memory too low for this command" in captured.out
    assert "Windows hint" in captured.out


def test_ensure_docker_healthy_ignores_memory_when_probe_missing(monkeypatch) -> None:
    cli = _load_silicium_module()

    monkeypatch.setattr(cli, "docker_health", lambda ctx, retries, timeout_s: cli.DockerHealth(True, "", "ok"))
    monkeypatch.setattr(cli, "docker_memory_bytes", lambda ctx, timeout_s=8.0: None)

    cli.ensure_docker_healthy(_make_ctx(cli), min_memory_bytes=2 * 1024 * 1024 * 1024)


def test_cmd_cpp_test_passes_memory_guard_to_docker_health(monkeypatch) -> None:
    cli = _load_silicium_module()
    ctx = _make_ctx(cli)
    ensure_calls: list[int | None] = []
    docker_runs: list[list[str]] = []

    def fake_ensure(ctx, retries, timeout_s, min_memory_bytes=None):
        ensure_calls.append(min_memory_bytes)

    def fake_ensure_image(image, ctx):
        return None

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_subprocess_run(cmd, **kwargs):
        docker_runs.append(list(cmd))
        return _Result()

    monkeypatch.delenv("SILICIUM_CPP_TEST_MIN_DOCKER_MEMORY_MB", raising=False)
    monkeypatch.setattr(cli, "ensure_docker_healthy", fake_ensure)
    monkeypatch.setattr(cli, "ensure_cpp_test_image", fake_ensure_image)
    monkeypatch.setattr(cli.subprocess, "run", fake_subprocess_run)

    args = argparse.Namespace(
        scope="executor",
        gtest_filter="",
        timeout=10,
        jobs=1,
        image="silicium/cpp-tests:latest",
        retry=1,
        use_ccache=False,
    )
    cli.cmd_cpp_test(args, ctx)

    assert ensure_calls == [2 * 1024 * 1024 * 1024]
    assert docker_runs


def test_command_wrapper_emits_structured_start_and_finish(monkeypatch, tmp_path: Path) -> None:
    cli = _load_silicium_module()
    ctx = _make_ctx(cli)
    log_path = tmp_path / "cli-structured.ndjson"

    monkeypatch.setenv("SILICIUM_CLI_STRUCTURED_LOG", str(log_path))
    monkeypatch.delenv("SILICIUM_RUN_ID", raising=False)
    monkeypatch.delenv("EXECUTOR_RUN_ID", raising=False)
    monkeypatch.delenv("WORKER_RUN_ID", raising=False)

    observed = {"run_id": ""}

    def fake_handler(args, inner_ctx):
        assert inner_ctx == ctx
        observed["run_id"] = os.environ.get("SILICIUM_RUN_ID", "")

    wrapped = cli.CommandRegistry._wrap(fake_handler, ctx)
    wrapped(argparse.Namespace(command="start"))

    assert observed["run_id"].startswith("cli-")
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    start_evt = json.loads(lines[0])
    end_evt = json.loads(lines[1])

    assert start_evt["event"] == "command_started"
    assert end_evt["event"] == "command_finished"
    assert start_evt["run_id"] == end_evt["run_id"] == observed["run_id"]
    assert start_evt["schema_version"] == 1
    assert end_evt["payload"]["exit_code"] == 0


def test_command_wrapper_exports_run_id_to_executor_and_worker(monkeypatch, tmp_path: Path) -> None:
    cli = _load_silicium_module()
    ctx = _make_ctx(cli)
    log_path = tmp_path / "cli-env.ndjson"
    monkeypatch.setenv("SILICIUM_CLI_STRUCTURED_LOG", str(log_path))
    monkeypatch.delenv("SILICIUM_RUN_ID", raising=False)
    monkeypatch.delenv("EXECUTOR_RUN_ID", raising=False)
    monkeypatch.delenv("WORKER_RUN_ID", raising=False)

    captured = {"silicium": "", "executor": "", "worker": ""}

    def fake_handler(_args, _ctx):
        captured["silicium"] = os.environ.get("SILICIUM_RUN_ID", "")
        captured["executor"] = os.environ.get("EXECUTOR_RUN_ID", "")
        captured["worker"] = os.environ.get("WORKER_RUN_ID", "")

    wrapped = cli.CommandRegistry._wrap(fake_handler, ctx)
    wrapped(argparse.Namespace(command="check"))

    assert captured["silicium"]
    assert captured["silicium"] == captured["executor"] == captured["worker"]


def test_cmd_start_emits_dispatch_target_event(monkeypatch, tmp_path: Path) -> None:
    cli = _load_silicium_module()
    ctx = _make_ctx(cli)
    log_path = tmp_path / "cli-dispatch.ndjson"
    monkeypatch.setenv("SILICIUM_CLI_STRUCTURED_LOG", str(log_path))
    monkeypatch.setattr(cli, "compose_base", lambda _ctx: ["docker", "compose"])
    monkeypatch.setattr(cli, "run", lambda cmd, **kwargs: 0)

    wrapped = cli.CommandRegistry._wrap(cli.cmd_start, ctx)
    wrapped(argparse.Namespace(command="start", target="localnet"))

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    dispatch = [evt for evt in events if evt.get("event") == "dispatch_target"]
    assert dispatch
    payload = dispatch[0]["payload"]
    assert payload["action"] == "compose_up"
    assert payload["target"] == "localnet"
    assert payload["service"] == "silicium-localnet"


def test_world_mode_defaults_enable_mesh_bootstrap(monkeypatch) -> None:
    cli = _load_silicium_module()
    parser = argparse.ArgumentParser()
    cli.configure_node_start(parser)
    args = parser.parse_args(["--world", "--world-name", "team-eu"])

    monkeypatch.setattr(cli, "_guess_world_advertise_host", lambda: "100.70.0.12")
    resolved = cli._apply_world_mode_defaults(args, node_id="france-1")

    assert resolved.gossip_enable is True
    assert resolved.relay_enable is True
    assert resolved.remote_dispatch_enable is True
    assert resolved.nat_punch_enable is True
    assert resolved.solana_reputation_enable is True
    assert resolved.gossip_bind == "0.0.0.0"
    assert resolved.peer_http_bind == "0.0.0.0"
    assert resolved.gossip_port == cli.WORLD_DEFAULT_GOSSIP_PORT
    assert resolved.peer_http_port == cli.WORLD_DEFAULT_PEER_HTTP_PORT
    assert resolved.gossip_advertise_host == "100.70.0.12"
    assert resolved.peer_advertise_host == "100.70.0.12"
    assert resolved.mesh_key.startswith("world:team-eu:")
    assert "world-identities/france-1/ed25519.pem" in resolved.identity_key_path


def test_node_start_enables_default_stun_with_nat_punch() -> None:
    cli = _load_silicium_module()
    parser = argparse.ArgumentParser()
    cli.configure_node_start(parser)
    args = parser.parse_args(["--nat-punch-enable", "--p2p-direct-transport-backend", "auto"])

    resolved = cli._apply_nat_traversal_defaults(args)

    assert resolved.p2p_stun_server == cli.DEFAULT_PUBLIC_STUN_SERVER


def test_node_start_forwards_release_telemetry(monkeypatch) -> None:
    cli = _load_silicium_module()
    parser = argparse.ArgumentParser()
    cli.configure_node_start(parser)
    args = parser.parse_args(
        [
            "--app-version",
            "0.2.9-dev.4",
            "--release-channel",
            "dev",
            "--release-build",
            "test-build",
            "--node-id",
            "telemetry-node",
            "--seed-peers",
            "http://seed-a.example,http://seed-b.example",
            "--peer-http-port",
            "46001",
        ]
    )
    monkeypatch.setattr(
        cli,
        "_resolve_mcp_settings",
        lambda _args: {"export_dir": ".silicium/test-export"},
    )

    monkeypatch.setattr(cli, "_p2p_node_command", lambda: ["p2p_node"])

    captured: dict[str, object] = {}

    def fake_run_p2p_node(command, env):
        captured["command"] = list(command)
        captured["env"] = dict(env)
        return 0

    monkeypatch.setattr(cli, "_run_p2p_node", fake_run_p2p_node)

    with pytest.raises(SystemExit) as exited:
        cli.cmd_node_start(args, _make_ctx(cli))

    assert exited.value.code == 0
    command = captured["command"]
    assert command[:3] == ["p2p_node", "--data-dir", ".silicium/test-export"]
    assert command[3] == "--dispatcher-seed"
    assert command[4].isdigit()
    env = captured["env"]
    assert env["SILICIUM_APP_VERSION"] == "0.2.9-dev.4"
    assert env["SILICIUM_RELEASE_CHANNEL"] == "dev"
    assert env["SILICIUM_RELEASE_BUILD"] == "test-build"
    assert env["SILICIUM_NODE_ID"] == "telemetry-node"
    assert env["SILICIUM_DATA_DIR"] == ".silicium/test-export"
    assert env["SILICIUM_BOOTSTRAP_PEERS"] == "http://seed-a.example,http://seed-b.example"
    assert env["API_PORT"] == "46001"
    assert env["SILICIUM_DISPATCH_SEED"].isdigit()


def test_node_start_uses_explicit_p2p_node_binary(monkeypatch) -> None:
    cli = _load_silicium_module()
    monkeypatch.setenv("SILICIUM_P2P_NODE_BIN", r"C:\\tmp\\p2p_node.exe")
    assert cli._p2p_node_command() == [r"C:\\tmp\\p2p_node.exe"]


def test_world_mode_merges_discovery_seeds(monkeypatch) -> None:
    cli = _load_silicium_module()
    parser = argparse.ArgumentParser()
    cli.configure_node_start(parser)
    args = parser.parse_args(
        [
            "--world",
            "--world-seeds",
            "https://seed-a.example,http://seed-b.example",
            "--discovery-seeds",
            "https://seed-a.example,http://seed-c.example",
        ]
    )

    monkeypatch.setattr(cli, "_guess_world_advertise_host", lambda: "100.70.0.12")
    resolved = cli._apply_world_mode_defaults(args, node_id="croatia-1")

    assert resolved.discovery_seeds == "https://seed-a.example,http://seed-c.example,http://seed-b.example"
