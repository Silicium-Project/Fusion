from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tools.cli  # noqa: E402


def _cli_modules() -> list:
    modules = [tools.cli]
    for info in pkgutil.walk_packages(tools.cli.__path__, "tools.cli."):
        if info.name != "tools.cli.__main__":
            modules.append(importlib.import_module(info.name))
    return modules


class _Cli:
    """Flat view of the `tools.cli` package (the CLI used to be one file)."""

    def __init__(self) -> None:
        self._modules = _cli_modules()

    def __getattr__(self, name: str):
        for module in self._modules:
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(name)

    def patch(self, monkeypatch, name: str, value) -> None:
        """Replace `name` in every CLI module that defines or imports it."""
        patched = False
        for module in self._modules:
            if name in vars(module):
                monkeypatch.setattr(module, name, value)
                patched = True
        assert patched, name


def _load_silicium_module() -> _Cli:
    return _Cli()


def _make_ctx(cli):
    return cli.Context(
        config=cli.EnvConfig(
            docker_bin="docker",
            docker_compose_bin=None,
            ledger_prefix="silicium",
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

    cli.patch(monkeypatch, "run", fake_run)
    cli.patch(monkeypatch, "cmd_workload_lint", fake_workload_lint)
    cli.patch(monkeypatch, "_run_entrypoint_posix_tests_in_docker", fake_posix)

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

    cli.patch(monkeypatch, "run", fake_run)
    cli.patch(monkeypatch, "cmd_workload_lint", fake_workload_lint)
    cli.patch(monkeypatch, "_run_entrypoint_posix_tests_in_docker", fake_posix)

    ctx = _make_ctx(cli)
    args = argparse.Namespace(entrypoint_docker=False, posix_pytest_image=cli.POSIX_PYTEST_IMAGE_DEFAULT)
    cli.cmd_test(args, ctx)

    assert posix_called["value"] is False
    pytest_cmds = [cmd for cmd in calls if cmd[:3] == [sys.executable, "-m", "pytest"]]
    assert len(pytest_cmds) == 1
    assert pytest_cmds[0] == [sys.executable, "-m", "pytest"]


def test_configure_check_exposes_active_scope() -> None:
    cli = _load_silicium_module()
    parser = argparse.ArgumentParser()
    cli.configure_check(parser)

    args = parser.parse_args([])
    assert args.scope == "platform"

    args = parser.parse_args(["--scope", "all", "--no-docker"])
    assert args.scope == "all"
    assert args.docker is False


def test_ensure_docker_healthy_fails_on_low_memory(monkeypatch, capsys) -> None:
    cli = _load_silicium_module()

    cli.patch(monkeypatch, "docker_health", lambda ctx, retries, timeout_s: cli.DockerHealth(True, "", "ok"))
    cli.patch(monkeypatch, "docker_memory_bytes", lambda ctx, timeout_s=8.0: 512 * 1024 * 1024)
    cli.patch(monkeypatch, "host_os_name", lambda: "nt")

    with pytest.raises(SystemExit) as exc:
        cli.ensure_docker_healthy(_make_ctx(cli), min_memory_bytes=2 * 1024 * 1024 * 1024)

    assert int(exc.value.code) == 1
    captured = capsys.readouterr()
    assert "Docker memory too low for this command" in captured.out
    assert "Windows hint" in captured.out


def test_ensure_docker_healthy_ignores_memory_when_probe_missing(monkeypatch) -> None:
    cli = _load_silicium_module()

    cli.patch(monkeypatch, "docker_health", lambda ctx, retries, timeout_s: cli.DockerHealth(True, "", "ok"))
    cli.patch(monkeypatch, "docker_memory_bytes", lambda ctx, timeout_s=8.0: None)

    cli.ensure_docker_healthy(_make_ctx(cli), min_memory_bytes=2 * 1024 * 1024 * 1024)


def test_command_wrapper_emits_structured_start_and_finish(monkeypatch, tmp_path: Path) -> None:
    cli = _load_silicium_module()
    ctx = _make_ctx(cli)
    log_path = tmp_path / "cli-structured.ndjson"

    monkeypatch.setenv("SILICIUM_CLI_STRUCTURED_LOG", str(log_path))
    monkeypatch.delenv("SILICIUM_RUN_ID", raising=False)

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


def test_command_wrapper_exports_run_id_to_network(monkeypatch, tmp_path: Path) -> None:
    cli = _load_silicium_module()
    ctx = _make_ctx(cli)
    log_path = tmp_path / "cli-env.ndjson"
    monkeypatch.setenv("SILICIUM_CLI_STRUCTURED_LOG", str(log_path))
    monkeypatch.delenv("SILICIUM_RUN_ID", raising=False)
    captured = {"silicium": ""}

    def fake_handler(_args, _ctx):
        captured["silicium"] = os.environ.get("SILICIUM_RUN_ID", "")

    wrapped = cli.CommandRegistry._wrap(fake_handler, ctx)
    wrapped(argparse.Namespace(command="check"))

    assert captured["silicium"]


def test_cmd_start_emits_dispatch_target_event(monkeypatch, tmp_path: Path) -> None:
    cli = _load_silicium_module()
    ctx = _make_ctx(cli)
    log_path = tmp_path / "cli-dispatch.ndjson"
    monkeypatch.setenv("SILICIUM_CLI_STRUCTURED_LOG", str(log_path))
    cli.patch(monkeypatch, "compose_base", lambda _ctx: ["docker", "compose"])
    cli.patch(monkeypatch, "run", lambda cmd, **kwargs: 0)

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

    cli.patch(monkeypatch, "_guess_world_advertise_host", lambda: "100.70.0.12")
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
    cli.patch(
        monkeypatch,
        "_resolve_mcp_settings",
        lambda _args: {"export_dir": ".silicium/test-export"},
    )

    captured: dict[str, object] = {}

    def fake_run_network_node(node_args, settings, node_id):
        captured["command"] = list(cli._network_node_args(args, settings, node_id))
        return 0

    cli.patch(monkeypatch, "_run_network_node", fake_run_network_node)

    with pytest.raises(SystemExit) as exited:
        cli.cmd_node_start(args, _make_ctx(cli))

    assert exited.value.code == 0
    command = captured["command"]
    assert command[:2] == ["--export-dir", ".silicium/test-export"]
    assert command[command.index("--node-id") + 1] == "telemetry-node"
    assert command[command.index("--app-version") + 1] == "0.2.9-dev.4"
    assert command[command.index("--release-channel") + 1] == "dev"
    assert command[command.index("--release-build") + 1] == "test-build"
    assert command[command.index("--peer-http-port") + 1] == "46001"
    assert command[command.index("--seed-peers") + 1] == "http://seed-a.example,http://seed-b.example"


def test_node_start_uses_explicit_p2p_node_binary(monkeypatch) -> None:
    cli = _load_silicium_module()
    monkeypatch.setenv("SILICIUM_P2P_NODE_BIN", r"C:\\tmp\\p2p_node.exe")
    assert cli._p2p_node_command() == [r"C:\\tmp\\p2p_node.exe"]


def test_node_start_never_builds_p2p_node_implicitly(monkeypatch, tmp_path: Path) -> None:
    cli = _load_silicium_module()
    monkeypatch.delenv("SILICIUM_P2P_NODE_BIN", raising=False)
    cli.patch(monkeypatch, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: r"C:\\cargo.exe")

    with pytest.raises(RuntimeError, match="set_SILICIUM_P2P_NODE_BIN"):
        cli._p2p_node_command()


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

    cli.patch(monkeypatch, "_guess_world_advertise_host", lambda: "100.70.0.12")
    resolved = cli._apply_world_mode_defaults(args, node_id="croatia-1")

    assert resolved.discovery_seeds == "https://seed-a.example,http://seed-c.example,http://seed-b.example"
