"""`workload list`, `workload show` and `workload queue`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.cli.constants import WORKLOAD_ROOT
from tools.cli.context import Context
from tools.cli.proc import COLOR_YELLOW, colorize
from tools.cli.workload.manifest import (
    _read_workload_manifest,
    _select_preset,
    _workload_dry_run_plan,
    _workload_entries,
    _workload_filter_summary,
    _workload_has_filters,
    _workload_matches_filters,
    _workload_metadata,
    _workload_preset_names,
    add_workload_filter_args,
)


def cmd_workload_list(args: argparse.Namespace, ctx: Context) -> None:
    entries = _workload_entries()
    if not entries:
        print("No workloads found.")
        return
    matches = [(path, data) for path, data in entries if _workload_matches_filters(data, args)]
    if not matches:
        if _workload_has_filters(args):
            print(f"No workloads match filters: {_workload_filter_summary(args)}")
        else:
            print("No workloads found.")
        return
    if args.json:
        payload = [_workload_metadata(path, data) for path, data in matches]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if args.details:
        header = [
            "path",
            "engine",
            "cpu",
            "gpu",
            "memory",
            "wall_sec",
            "cpu_sec",
            "budget_mem",
            "resource_profile",
            "determinism",
            "presets",
        ]
        print("\t".join(header))
        for path, data in matches:
            resources = data.get("resources", {})
            taxonomy = data.get("taxonomy", {})
            budget = resources.get("budget", {}) if isinstance(resources, dict) else {}
            row = [
                path,
                str(data.get("engine", "-")),
                str(resources.get("cpu", "-")),
                str(resources.get("gpu", "-")),
                str(resources.get("memory", "-")),
                str(budget.get("wall_sec", "-")),
                str(budget.get("cpu_sec", "-")),
                str(budget.get("memory", "-")),
                str(taxonomy.get("resource_profile", "-")),
                str(taxonomy.get("determinism", "-")),
                ",".join(_workload_preset_names(data)) or "-",
            ]
            print("\t".join(row))
        return
    paths = [path for path, _ in matches]
    if not args.tree:
        for path in paths:
            print(path)
        return

    def insert(node: dict, parts: list[str]) -> None:
        if not parts:
            return
        head, *tail = parts
        child = node.setdefault(head, {})
        insert(child, tail)

    tree: dict = {}
    for path in paths:
        insert(tree, path.split("/"))

    def print_tree(node: dict, depth: int = 0) -> None:
        for name in sorted(node):
            child = node[name]
            prefix = "  " * depth + "- "
            print(f"{prefix}{name}")
            print_tree(child, depth + 1)

    print_tree(tree)


def configure_workload_list(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Display full tree instead of compact list.",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Display metadata table for workloads.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output workload metadata as JSON.",
    )
    add_workload_filter_args(parser)


def cmd_workload_show(args: argparse.Namespace, ctx: Context) -> None:
    manifest = WORKLOAD_ROOT / args.path / "manifest.yaml"
    if not manifest.exists():
        print(f"Manifest not found: {manifest}")
        sys.exit(1)
    data = _read_workload_manifest(manifest)
    if not _workload_matches_filters(data, args):
        print(f"Manifest does not match filters: {_workload_filter_summary(args)}")
        sys.exit(1)
    if args.preset and not args.dry_run:
        print("--preset requires --dry-run.")
        sys.exit(1)
    if args.dry_run:
        if args.preset and not _select_preset(data, args.preset):
            available = ", ".join(_workload_preset_names(data)) or "-"
            print(f"Preset not found: {args.preset}")
            print(f"Available presets: {available}")
            sys.exit(1)
        plan = _workload_dry_run_plan(args.path, manifest, data, args.preset)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return
    if args.meta:
        meta = _workload_metadata(args.path, data)
        resources = meta["resources"]
        taxonomy = meta["taxonomy"]
        presets = meta["presets"]
        budget = resources.get("budget", {}) if isinstance(resources, dict) else {}
        print(f"Path: {meta['path']}")
        print(f"ID: {meta.get('id', '-')}")
        print(f"Engine: {meta.get('engine', '-')}")
        print(
            f"Resources: cpu={resources.get('cpu', '-')} "
            f"gpu={resources.get('gpu', '-')} memory={resources.get('memory', '-')}"
        )
        if budget:
            print(
                f"Budget: wall_sec={budget.get('wall_sec', '-')} "
                f"cpu_sec={budget.get('cpu_sec', '-')} memory={budget.get('memory', '-')}"
            )
        print(
            f"Taxonomy: category={taxonomy.get('category', '-')} "
            f"domain={taxonomy.get('domain', '-')} "
            f"complexity={taxonomy.get('complexity', '-')} "
            f"resource_profile={taxonomy.get('resource_profile', '-')} "
            f"determinism={taxonomy.get('determinism', '-')}"
        )
        print(f"Presets: {', '.join(presets) if presets else '-'}")
        return
    print(colorize(f"==> {manifest}", COLOR_YELLOW))
    print(manifest.read_text(encoding="utf-8"))
    if args.readme:
        readme = manifest.with_name("README.md")
        if readme.exists():
            print(colorize(f"\n==> {readme}", COLOR_YELLOW))
            print(readme.read_text(encoding="utf-8"))
        else:
            print("No README.md for this workload.")


def configure_workload_show(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        help="Workload path (e.g., calcul/math-simulation).",
    )
    add_workload_filter_args(parser)
    parser.add_argument(
        "--readme",
        action="store_true",
        help="Also display README.md if present.",
    )
    parser.add_argument(
        "--meta",
        action="store_true",
        help="Show metadata summary and presets.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print deterministic execution plan as JSON.",
    )
    parser.add_argument(
        "--preset",
        help="Preset name to apply with --dry-run.",
    )


def cmd_workload_queue(args: argparse.Namespace, ctx: Context) -> None:
    summary = Path(args.summary)
    if not summary.exists():
        print(f"Summary not found: {summary}")
        sys.exit(1)
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Failed to parse summary JSON: {exc}")
        sys.exit(1)

    partitions = data.get("partitions", [])
    ids = [p.get("id") for p in partitions if isinstance(p, dict) and p.get("id")]
    if not ids:
        print("No partitions found in summary.")
        sys.exit(1)

    dest = Path(args.output or summary.parent / "queue.txt")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(ids) + "\n", encoding="utf-8")
    print(colorize(f"Wrote {len(ids)} entries to {dest}", COLOR_YELLOW))


def configure_workload_queue(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--summary",
        required=True,
        help="Path to a workload summary JSON file.",  # i18n:ignore
    )
    parser.add_argument(
        "--output",
        help="Destination queue file (default: <summary_dir>/queue.txt).",
    )
