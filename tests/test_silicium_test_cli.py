from __future__ import annotations

import argparse
import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path


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

    def fake_ensure_docker_healthy(ctx, retries, timeout_s):
        return None

    def fake_run_core_check_in_docker(env_vars, ctx):
        docker_calls.append(dict(env_vars))

    monkeypatch.setattr(cli.os, "name", "nt")
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
