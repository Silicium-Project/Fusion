"""Execution context: environment configuration (Docker binaries, config file)
and MCP settings resolution.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tools.cli.constants import (
    DEFAULT_CONFIG_FILE,
    MCP_DEFAULT_BIND,
    MCP_DEFAULT_EXPORT_DIR,
    MCP_DEFAULT_PORT,
    MCP_DEFAULT_TOKEN_FILE,
    REPO_ROOT,
)


@dataclass(frozen=True)
class EnvConfig:
    docker_bin: str
    docker_compose_bin: str | None
    ledger_prefix: str


@dataclass(frozen=True)
class Context:
    config: EnvConfig


@dataclass(frozen=True)
class DockerHealth:
    ok: bool
    error_code: str
    message: str
    detail: str = ""


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_config_file() -> Path:
    override = os.environ.get("SILICIUM_CONFIG", "").strip()
    if override:
        return Path(override)
    return DEFAULT_CONFIG_FILE


def _resolve_repo_path(value: str, base: Path = REPO_ROOT) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return base / p


def _ensure_token_file(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    # Atomic write: a concurrent reader never sees an empty token file.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(token, encoding="utf-8")
    os.replace(tmp, path)
    return token


def _resolve_mcp_settings(args: argparse.Namespace) -> dict[str, Any]:
    cfg = _load_json_file(_resolve_config_file()).get("mcp", {})
    if not isinstance(cfg, dict):
        cfg = {}

    bind = getattr(args, "bind", "") or os.environ.get("SILICIUM_MCP_BIND", "") or str(cfg.get("bind") or MCP_DEFAULT_BIND)
    port = getattr(args, "port", 0) or int(os.environ.get("SILICIUM_MCP_PORT", "0") or 0) or int(cfg.get("port") or MCP_DEFAULT_PORT)

    export_dir_value = (
        getattr(args, "export_dir", "")
        or os.environ.get("SILICIUM_MCP_EXPORT_DIR", "")
        or str(cfg.get("export_dir") or MCP_DEFAULT_EXPORT_DIR)
    )
    export_dir = _resolve_repo_path(export_dir_value) if export_dir_value else MCP_DEFAULT_EXPORT_DIR

    token_file_value = os.environ.get("SILICIUM_MCP_TOKEN_FILE", "") or str(cfg.get("token_file") or MCP_DEFAULT_TOKEN_FILE)
    token_file = _resolve_repo_path(token_file_value)

    enable_tools = bool(getattr(args, "enable_tools", False))
    if not getattr(args, "enable_tools", False):
        env_enable = os.environ.get("SILICIUM_MCP_ENABLE_TOOLS", "").strip().lower()
        if env_enable:
            enable_tools = env_enable not in {"0", "false", "no"}
        else:
            enable_tools = bool(cfg.get("enable_tools") or False)

    def _split_csv(raw: str) -> list[str]:
        return [item.strip() for item in str(raw).split(",") if item.strip()]

    def _resolve_list_value(arg_name: str, env_name: str, cfg_name: str) -> list[str]:
        arg_raw = str(getattr(args, arg_name, "") or "").strip()
        if arg_raw:
            return _split_csv(arg_raw)
        env_raw = str(os.environ.get(env_name, "")).strip()
        if env_raw:
            return _split_csv(env_raw)
        cfg_raw = cfg.get(cfg_name, [])
        if isinstance(cfg_raw, str):
            return _split_csv(cfg_raw)
        if isinstance(cfg_raw, list):
            return [str(item).strip() for item in cfg_raw if str(item).strip()]
        return []

    no_auth = bool(getattr(args, "no_auth", False))
    token = ""
    if not no_auth:
        token = getattr(args, "token", "") or os.environ.get("SILICIUM_MCP_TOKEN", "") or _ensure_token_file(token_file)
    tool_allowlist = _resolve_list_value("tool_allowlist", "SILICIUM_MCP_TOOL_ALLOWLIST", "tool_allowlist")
    tool_denylist = _resolve_list_value("tool_denylist", "SILICIUM_MCP_TOOL_DENYLIST", "tool_denylist")
    resource_allowlist = _resolve_list_value("resource_allowlist", "SILICIUM_MCP_RESOURCE_ALLOWLIST", "resource_allowlist")
    resource_denylist = _resolve_list_value("resource_denylist", "SILICIUM_MCP_RESOURCE_DENYLIST", "resource_denylist")

    export_dir.mkdir(parents=True, exist_ok=True)
    return {
        "bind": bind,
        "port": port,
        "export_dir": str(export_dir),
        "token": token,
        "no_auth": no_auth,
        "enable_tools": enable_tools,
        "tool_allowlist": tool_allowlist,
        "tool_denylist": tool_denylist,
        "resource_allowlist": resource_allowlist,
        "resource_denylist": resource_denylist,
    }


def _mcp_base_url(settings: Mapping[str, Any]) -> str:
    return f"http://{settings['bind']}:{settings['port']}"


def load_env_config(env: Mapping[str, str] | None = None) -> EnvConfig:
    source = os.environ if env is None else env
    return EnvConfig(
        docker_bin=source.get("DOCKER", "docker"),
        docker_compose_bin=source.get("DOCKER_COMPOSE_BIN"),
        ledger_prefix=source.get("SILICIUM_LEDGER_PREFIX", "silicium"),
    )


def build_context(env: Mapping[str, str] | None = None) -> Context:
    return Context(config=load_env_config(env))
