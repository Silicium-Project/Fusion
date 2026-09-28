"""`mcp serve` and `mcp print-config`.
"""

from __future__ import annotations

import argparse
import json

from tools.cli.context import Context, _mcp_base_url, _resolve_mcp_settings


def configure_mcp_serve(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bind", default="", help="Bind address (default: from config/env or 127.0.0.1).")
    parser.add_argument("--port", type=int, default=0, help="HTTP port (default: from config/env or 9765).")
    parser.add_argument("--export-dir", default="", help="MCP export directory (default: from config/env).")
    parser.add_argument("--snapshot-dir", default="", help="Enable persistent snapshots in this directory.")
    parser.add_argument("--snapshot-max-files", type=int, default=None, help="Max number of snapshots kept (0 disables cap).")
    parser.add_argument("--snapshot-max-bytes", type=int, default=None, help="Max total snapshot bytes (0 disables cap).")
    parser.add_argument("--enable-tools", action="store_true", help="Enable guarded control tools.")
    parser.add_argument("--tool-allowlist", default="", help="Comma-separated allowed MCP tool names/patterns.")
    parser.add_argument("--tool-denylist", default="", help="Comma-separated denied MCP tool names/patterns.")
    parser.add_argument("--resource-allowlist", default="", help="Comma-separated allowed MCP resource URI patterns.")
    parser.add_argument("--resource-denylist", default="", help="Comma-separated denied MCP resource URI patterns.")
    parser.add_argument("--token", default="", help="Bearer token (default: from token file/config/env).")
    parser.add_argument("--no-auth", action="store_true", help="Disable bearer auth for this server run.")
    parser.add_argument("--log-format", choices=["text", "json"], default="", help="MCP server logs format override.")


def cmd_mcp_serve(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)  # keep signature consistent
    settings = _resolve_mcp_settings(args)
    from tools import mcp_server

    argv = [
        "--bind",
        str(settings["bind"]),
        "--port",
        str(settings["port"]),
        "--export-dir",
        str(settings["export_dir"]),
    ]
    if getattr(args, "snapshot_dir", ""):
        argv.extend(["--snapshot-dir", str(args.snapshot_dir)])
    if getattr(args, "snapshot_max_files", None) is not None:
        argv.extend(["--snapshot-max-files", str(args.snapshot_max_files)])
    if getattr(args, "snapshot_max_bytes", None) is not None:
        argv.extend(["--snapshot-max-bytes", str(args.snapshot_max_bytes)])
    if settings["no_auth"]:
        argv.append("--no-auth")
    else:
        argv.extend(["--token", str(settings["token"])])
    if settings["tool_allowlist"]:
        argv.extend(["--tool-allowlist", ",".join(str(x) for x in settings["tool_allowlist"])])
    if settings["tool_denylist"]:
        argv.extend(["--tool-denylist", ",".join(str(x) for x in settings["tool_denylist"])])
    if settings["resource_allowlist"]:
        argv.extend(["--resource-allowlist", ",".join(str(x) for x in settings["resource_allowlist"])])
    if settings["resource_denylist"]:
        argv.extend(["--resource-denylist", ",".join(str(x) for x in settings["resource_denylist"])])
    if getattr(args, "log_format", ""):
        argv.extend(["--log-format", str(args.log_format)])
    if settings["enable_tools"]:
        argv.append("--enable-tools")
    raise SystemExit(mcp_server.main(argv))


def configure_mcp_print_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["json", "env"], default="json", help="Output format.")
    parser.add_argument("--bind", default="", help="Override bind address for output.")
    parser.add_argument("--port", type=int, default=0, help="Override port for output.")
    parser.add_argument("--export-dir", default="", help="Override export directory for output.")
    parser.add_argument("--token", default="", help="Override token for output.")
    parser.add_argument("--enable-tools", action="store_true", help="Enable tools in output (does not start server).")


def cmd_mcp_print_config(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    base_url = _mcp_base_url(settings)
    if args.format == "env":
        print(f"SILICIUM_MCP_URL={base_url}")
        print(f"SILICIUM_MCP_TOKEN={settings['token']}")
        print(f"SILICIUM_MCP_EXPORT_DIR={settings['export_dir']}")
        print(f"SILICIUM_MCP_ENABLE_TOOLS={'1' if settings['enable_tools'] else '0'}")
        print(f"SILICIUM_MCP_TOOL_ALLOWLIST={','.join(str(x) for x in settings['tool_allowlist'])}")
        print(f"SILICIUM_MCP_TOOL_DENYLIST={','.join(str(x) for x in settings['tool_denylist'])}")
        print(f"SILICIUM_MCP_RESOURCE_ALLOWLIST={','.join(str(x) for x in settings['resource_allowlist'])}")
        print(f"SILICIUM_MCP_RESOURCE_DENYLIST={','.join(str(x) for x in settings['resource_denylist'])}")
        return
    print(
        json.dumps(
            {
                "base_url": base_url,
                "token": settings["token"],
                "export_dir": settings["export_dir"],
                "enable_tools": settings["enable_tools"],
                "tool_allowlist": settings["tool_allowlist"],
                "tool_denylist": settings["tool_denylist"],
                "resource_allowlist": settings["resource_allowlist"],
                "resource_denylist": settings["resource_denylist"],
            },
            indent=2,
            sort_keys=True,
        )
    )
