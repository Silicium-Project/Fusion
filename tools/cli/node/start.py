"""`node start`: world-mode and NAT defaults, then launch of the Python
network node (default) or of the experimental Rust `p2p_node`.

The command is split by responsibility:

- `start_options.py`: the argument parser (`configure_node_start`)
- `world_mode.py`: `--world` defaults (`_apply_world_mode_defaults`)
- `network_args.py`: argv of the Python daemon (`_network_node_args`)
- `p2p_experiment.py`: the opt-in Rust `p2p_node` launcher

`_run_network_node` and `_run_p2p_node` are looked up in this module by
`cmd_node_start`, so tests replace them here (`cli.patch(...)` patches every
CLI module that defines or imports the name).
"""

from __future__ import annotations

import argparse
import secrets
from typing import Any, Mapping

from tools.cli.context import Context, _resolve_mcp_settings
from tools.cli.node.network_args import _network_node_args
from tools.cli.node.p2p_experiment import (
    _build_p2p_node_env,
    _p2p_node_args,
    _p2p_node_command,
    _run_p2p_node,
)
from tools.cli.node.start_options import configure_node_start
from tools.cli.node.world_mode import _apply_world_mode_defaults
from tools.node_defaults import apply_nat_traversal_defaults as _apply_nat_traversal_defaults

__all__ = ["cmd_node_start", "configure_node_start"]


def _run_network_node(
    args: argparse.Namespace,
    settings: Mapping[str, Any],
    node_id: str,
) -> int:
    """Run the integrated Python daemon in-process and return its exit code."""
    from tools import network_node

    return int(network_node.main(_network_node_args(args, settings, node_id)))


def cmd_node_start(args: argparse.Namespace, ctx: Context) -> None:
    """Start the node; always exits (SystemExit) with the node exit code."""
    (void := ctx)
    settings = _resolve_mcp_settings(args)

    node_id = args.node_id or f"node-{secrets.token_hex(4)}"
    args = _apply_world_mode_defaults(args, node_id=node_id)
    args = _apply_nat_traversal_defaults(args)
    if not bool(getattr(args, "experimental_p2p_node", False)):
        raise SystemExit(_run_network_node(args, settings, node_id))

    # The Rust p2p_node is retained as an explicitly opt-in experiment.  It is
    # not the production node because it does not publish the integrated
    # heartbeat and peer registry consumed by the site.
    command = _p2p_node_command()
    env = _build_p2p_node_env(args, settings, node_id)
    p2p_args = _p2p_node_args(args, settings, node_id)
    raise SystemExit(_run_p2p_node([*command, *p2p_args], env))
