"""Command tree: registers every command and builds the argument parser.
"""

from __future__ import annotations

import argparse
import os

from tools.cli.commands.checks import (
    cmd_budget,
    cmd_check,
    cmd_clean,
    cmd_doctor,
    cmd_smoke,
    cmd_test,
    configure_budget,
    configure_check,
    configure_clean,
    configure_doctor,
    configure_smoke,
    configure_test,
)
from tools.cli.commands.ledger import (
    cmd_ledger_export,
    cmd_ledger_import,
    cmd_ledger_list,
    cmd_ledger_wipe,
    configure_ledger_export,
    configure_ledger_import,
    configure_ledger_list,
    configure_ledger_wipe,
)
from tools.cli.commands.mcp import (
    cmd_mcp_print_config,
    cmd_mcp_serve,
    configure_mcp_print_config,
    configure_mcp_serve,
)
from tools.cli.commands.services import (
    cmd_alias,
    cmd_exec,
    cmd_history_clear,
    cmd_history_show,
    cmd_logs,
    cmd_setup_down,
    cmd_setup_up,
    cmd_start,
    cmd_status,
    cmd_stop,
    configure_alias,
    configure_exec,
    configure_history_clear,
    configure_history_show,
    configure_logs,
    configure_setup_down,
    configure_setup_up,
    configure_start,
    configure_status,
    configure_stop,
)
from tools.cli.commands.tui import cmd_tui, configure_tui
from tools.cli.context import Context
from tools.cli.framework import CommandGroup, CommandRegistry, CommandSpec
from tools.cli.interactive import cmd_shell, configure_shell
from tools.cli.node.api import (
    cmd_node_bootstrap_worker,
    cmd_node_create_job,
    cmd_node_fetch_fragment,
    cmd_node_fetch_job,
    cmd_node_get_heartbeat,
    cmd_node_get_metrics,
    cmd_node_get_peers,
    cmd_node_get_request,
    cmd_node_get_result,
    cmd_node_get_task,
    cmd_node_submit_request,
    cmd_node_submit_task,
    configure_node_bootstrap_worker,
    configure_node_create_job,
    configure_node_fetch_fragment,
    configure_node_fetch_job,
    configure_node_get,
    configure_node_get_local_file,
    configure_node_submit_request,
    configure_node_submit_task,
)
from tools.cli.node.start import cmd_node_start, configure_node_start
from tools.cli.workload.commands import (
    cmd_workload_list,
    cmd_workload_queue,
    cmd_workload_show,
    configure_workload_list,
    configure_workload_queue,
    configure_workload_show,
)
from tools.cli.workload.golden import (
    cmd_workload_alignment,
    cmd_workload_golden,
    configure_workload_alignment,
    configure_workload_golden,
)
from tools.cli.workload.lint import (
    cmd_workload_fixtures,
    cmd_workload_index,
    cmd_workload_lint,
    configure_workload_fixtures,
    configure_workload_index,
    configure_workload_lint,
)
from tools.i18n import set_runtime_locale, tr


def build_registry() -> CommandRegistry:
    registry = CommandRegistry()
    registry.add(CommandSpec("test", "Install dev deps and run pytest", configure_test, cmd_test))
    registry.add(CommandSpec("check", "Run core stability checks", configure_check, cmd_check))
    registry.add(CommandSpec("doctor", "Run environment diagnostics", configure_doctor, cmd_doctor))
    registry.add(CommandSpec("budget", "Measure command metrics against budgets", configure_budget, cmd_budget))
    registry.add(CommandSpec("smoke", "Run the proxy smoke test", configure_smoke, cmd_smoke))
    registry.add(CommandSpec("clean", "Clean caches/ledgers", configure_clean, cmd_clean))
    registry.add(CommandSpec("start", "Start a Silicium service", configure_start, cmd_start))
    registry.add(CommandSpec("stop", "Stop services", configure_stop, cmd_stop))
    registry.add(CommandSpec("status", "Show docker compose ps", configure_status, cmd_status))
    registry.add(CommandSpec("logs", "Tail service logs", configure_logs, cmd_logs))
    registry.add(CommandSpec("exec", "Run command in a service container", configure_exec, cmd_exec))
    registry.add(CommandSpec("alias", "Install helper function/aliases in shell rc", configure_alias, cmd_alias))
    registry.add(CommandSpec("tui", "Launch terminal UI", configure_tui, cmd_tui))
    registry.add(CommandSpec("shell", "Start interactive shell", configure_shell, cmd_shell))

    registry.add_group(
        CommandGroup(
            name="mcp",
            help=tr("cli.mcp.help"),
            dest="mcp_cmd",
            commands=[
                CommandSpec("serve", tr("cli.mcp.serve.help"), configure_mcp_serve, cmd_mcp_serve),
                CommandSpec("print-config", tr("cli.mcp.print_config.help"), configure_mcp_print_config, cmd_mcp_print_config),
            ],
        )
    )

    registry.add_group(
        CommandGroup(
            name="node",
            help="Run a role-aware Silicium network node daemon",
            dest="node_cmd",
            commands=[
                CommandSpec("start", "Start the local network node daemon", configure_node_start, cmd_node_start),
                CommandSpec("submit-task", "Submit a role-aware network task", configure_node_submit_task, cmd_node_submit_task),
                CommandSpec("get-task", "Read a submitted network task", configure_node_get, cmd_node_get_task),
                CommandSpec("get-result", "Read a task/request result", configure_node_get, cmd_node_get_result),
                CommandSpec("submit-request", "Submit a fast network request", configure_node_submit_request, cmd_node_submit_request),
                CommandSpec("get-request", "Read a submitted network request", configure_node_get, cmd_node_get_request),
                CommandSpec("create-job", "Create a Solana job and optionally enqueue a task", configure_node_create_job, cmd_node_create_job),
                CommandSpec("fetch-job", "Fetch a Solana job account", configure_node_fetch_job, cmd_node_fetch_job),
                CommandSpec("fetch-fragment", "Fetch a Solana fragment account", configure_node_fetch_fragment, cmd_node_fetch_fragment),
                CommandSpec("bootstrap-worker", "Register the current Solana worker on-chain", configure_node_bootstrap_worker, cmd_node_bootstrap_worker),
                CommandSpec("get-heartbeat", "Read the latest local node heartbeat", configure_node_get_local_file, cmd_node_get_heartbeat),
                CommandSpec("get-metrics", "Read the latest local node metrics", configure_node_get_local_file, cmd_node_get_metrics),
                CommandSpec("get-peers", "Read the latest local node peer snapshot", configure_node_get_local_file, cmd_node_get_peers),
            ],
        )
    )

    registry.add_group(
        CommandGroup(
            name="setup",
            help="Bootstrap and stop local stack",
            dest="setup_cmd",
            commands=[
                CommandSpec("up", "Bootstrap/start selected targets", configure_setup_up, cmd_setup_up),
                CommandSpec("down", "Stop/cleanup selected targets", configure_setup_down, cmd_setup_down),
            ],
        )
    )
    registry.add_group(
        CommandGroup(
            name="ledger",
            help="Manage ledger volumes",
            dest="ledger_cmd",
            commands=[
                CommandSpec("list", "List managed ledger volumes", configure_ledger_list, cmd_ledger_list),
                CommandSpec("wipe", "Delete ledger volumes", configure_ledger_wipe, cmd_ledger_wipe),
                CommandSpec("export", "Archive a ledger volume", configure_ledger_export, cmd_ledger_export),
                CommandSpec("import", "Restore a ledger volume", configure_ledger_import, cmd_ledger_import),
            ],
        )
    )
    registry.add_group(
        CommandGroup(
            name="workload",
            help="Inspect workload manifests",
            dest="workload_cmd",
            commands=[
                CommandSpec("list", "List workloads", configure_workload_list, cmd_workload_list),
                CommandSpec("show", "Show a workload manifest", configure_workload_show, cmd_workload_show),
                CommandSpec("queue", "Generate a queue file from a summary.json", configure_workload_queue, cmd_workload_queue),
                CommandSpec("lint", "Validate workload manifests against schema", configure_workload_lint, cmd_workload_lint),
                CommandSpec(
                    "index",
                    "Regenerate workloads/index.json from the manifests",  # i18n:ignore -- developer command
                    configure_workload_index,
                    cmd_workload_index,
                ),
                CommandSpec(
                    "fixtures",
                    "Validate workload fixture integrity",
                    configure_workload_fixtures,
                    cmd_workload_fixtures,
                ),
                CommandSpec(
                    "alignment",
                    "Report workload to fixture alignment",
                    configure_workload_alignment,
                    cmd_workload_alignment,
                ),
                CommandSpec(
                    "golden",
                    "Validate deterministic golden corpus",
                    configure_workload_golden,
                    cmd_workload_golden,
                ),
            ],
        )
    )
    registry.add_group(
        CommandGroup(
            name="history",
            help="Inspect Silicium shell history",
            dest="history_cmd",
            commands=[
                CommandSpec("show", "Display history entries", configure_history_show, cmd_history_show),
                CommandSpec("clear", "Purge history file", configure_history_clear, cmd_history_clear),
            ],
        )
    )

    return registry


def build_parser(ctx: Context) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="silicium",
        description="Silicium CLI and shell",
    )
    parser.add_argument(
        "--locale",
        default=os.environ.get("SILICIUM_LOCALE", ""),
        help="UI locale (e.g. en-US, fr-FR).",
    )
    # Kept as no-op global options for supervisors from pre-2.0 desktop installs.
    parser.add_argument("--pull-tasks-enable", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pull-tasks-interval-s", type=int, default=0, help=argparse.SUPPRESS)
    registry = build_registry()
    registry.register(parser, ctx)
    return parser


def execute(argv: list[str], ctx: Context) -> None:
    parser = build_parser(ctx)
    args = parser.parse_args(argv)
    set_runtime_locale(getattr(args, "locale", None))
    args.func(args)
