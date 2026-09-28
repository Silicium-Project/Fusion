"""Workload manifest reading: entries, filters, presets, command rendering
and dry-run plans.
"""

from __future__ import annotations

import argparse
import string
import sys
from pathlib import Path
from typing import Any, Mapping

from tools.cli.constants import (
    WORKLOAD_ROOT,
    WORKLOAD_TAXONOMY_CATEGORIES,
    WORKLOAD_TAXONOMY_COMPLEXITIES,
    WORKLOAD_TAXONOMY_DETERMINISM,
    WORKLOAD_TAXONOMY_DOMAINS,
    WORKLOAD_TAXONOMY_RESOURCE_PROFILES,
    WORKLOAD_TAXONOMY_TAGS,
)


def _read_workload_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        print("PyYAML is required for workload commands. Install with: python -m pip install pyyaml")
        sys.exit(1)
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Failed to parse manifest {manifest_path}: {exc}")
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"Invalid manifest (expected mapping): {manifest_path}")
        sys.exit(1)
    return data


def _workload_entries() -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    for path in workload_paths():
        manifest = WORKLOAD_ROOT / path / "manifest.yaml"
        entries.append((path, _read_workload_manifest(manifest)))
    return entries


def _workload_has_filters(args: argparse.Namespace) -> bool:
    return bool(
        args.category
        or args.domain
        or args.complexity
        or args.resource_profile
        or args.determinism
        or args.tag
    )


def _workload_filter_summary(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if args.category:
        parts.append(f"category={args.category}")
    if args.domain:
        parts.append(f"domain={args.domain}")
    if args.complexity:
        parts.append(f"complexity={args.complexity}")
    if args.resource_profile:
        parts.append(f"resource_profile={args.resource_profile}")
    if args.determinism:
        parts.append(f"determinism={args.determinism}")
    if args.tag:
        parts.append("tags=" + ",".join(args.tag))
    return " ".join(parts)


def _workload_matches_filters(data: dict[str, Any], args: argparse.Namespace) -> bool:
    if not _workload_has_filters(args):
        return True
    taxonomy = data.get("taxonomy")
    if not isinstance(taxonomy, dict):
        return False
    if args.category and taxonomy.get("category") != args.category:
        return False
    if args.domain and taxonomy.get("domain") != args.domain:
        return False
    if args.complexity and taxonomy.get("complexity") != args.complexity:
        return False
    if args.resource_profile and taxonomy.get("resource_profile") != args.resource_profile:
        return False
    if args.determinism and taxonomy.get("determinism") != args.determinism:
        return False
    if args.tag:
        tags = taxonomy.get("tags", [])
        if not isinstance(tags, list):
            return False
        tag_set = {str(item) for item in tags}
        if not set(args.tag).issubset(tag_set):
            return False
    determinism = taxonomy.get("determinism")
    if determinism == "deterministic":
        tags = taxonomy.get("tags", [])
        tag_set = {str(item) for item in tags} if isinstance(tags, list) else set()
        if "deterministic" not in tag_set:
            return False
    if determinism in {"bounded_stochastic", "stochastic"}:
        tags = taxonomy.get("tags", [])
        tag_set = {str(item) for item in tags} if isinstance(tags, list) else set()
        if "stochastic" not in tag_set:
            return False
    return True


def _workload_presets(data: dict[str, Any]) -> list[dict[str, Any]]:
    presets = data.get("presets", [])
    if not isinstance(presets, list):
        return []
    valid: list[dict[str, Any]] = []
    for preset in presets:
        if isinstance(preset, dict):
            name = preset.get("name")
            vars_map = preset.get("vars", {})
            if isinstance(name, str) and name and isinstance(vars_map, dict):
                valid.append(preset)
    return valid


def _workload_preset_names(data: dict[str, Any]) -> list[str]:
    return [str(preset.get("name")) for preset in _workload_presets(data)]


def _select_preset(data: dict[str, Any], name: str | None) -> dict[str, Any] | None:
    presets = _workload_presets(data)
    if not presets:
        return None
    if name:
        for preset in presets:
            if preset.get("name") == name:
                return preset
        return None
    if len(presets) == 1:
        return presets[0]
    for preset in presets:
        if preset.get("name") == "default":
            return preset
    return None


def _extract_placeholders(command: str) -> list[str]:
    placeholders: list[str] = []
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(command):
        if not field_name:
            continue
        name = field_name.split(".", 1)[0].split("[", 1)[0]
        if name not in placeholders:
            placeholders.append(name)
    return placeholders


def _render_command(command: str, variables: Mapping[str, Any]) -> str:
    rendered = command
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered


def _workload_metadata(path: str, data: dict[str, Any]) -> dict[str, Any]:
    resources = data.get("resources", {})
    taxonomy = data.get("taxonomy", {})
    presets = _workload_preset_names(data)
    return {
        "path": path,
        "id": data.get("id"),
        "engine": data.get("engine"),
        "resources": resources if isinstance(resources, dict) else {},
        "taxonomy": taxonomy if isinstance(taxonomy, dict) else {},
        "payment": data.get("payment", {}),
        "presets": presets,
    }


def _workload_dry_run_plan(path: str, manifest: Path, data: dict[str, Any], preset_name: str | None) -> dict[str, Any]:
    command = str(data.get("command") or "")
    preset = _select_preset(data, preset_name)
    variables = {}
    if preset:
        vars_map = preset.get("vars", {})
        if isinstance(vars_map, dict):
            variables = vars_map
    placeholders = _extract_placeholders(command)
    missing = [name for name in placeholders if name not in variables]
    plan = _workload_metadata(path, data)
    plan.update(
        {
            "manifest": str(manifest),
            "command": _render_command(command, variables),
            "placeholders": placeholders,
            "variables": variables,
            "missing_variables": missing,
            "preset": preset.get("name") if preset else None,
            "artifacts": data.get("artifacts", {}),
        }
    )
    return plan


def workload_paths() -> list[str]:
    if not WORKLOAD_ROOT.exists():
        return []
    paths: list[str] = []
    for manifest in WORKLOAD_ROOT.rglob("manifest.yaml"):
        rel = manifest.parent.relative_to(WORKLOAD_ROOT)
        paths.append(str(rel).replace("\\", "/"))
    return sorted(paths)


def add_workload_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--category",
        choices=WORKLOAD_TAXONOMY_CATEGORIES,
        help="Filter by workload category.",
    )
    parser.add_argument(
        "--domain",
        choices=WORKLOAD_TAXONOMY_DOMAINS,
        help="Filter by workload domain.",
    )
    parser.add_argument(
        "--complexity",
        choices=WORKLOAD_TAXONOMY_COMPLEXITIES,
        help="Filter by complexity level.",
    )
    parser.add_argument(
        "--resource-profile",
        dest="resource_profile",
        choices=WORKLOAD_TAXONOMY_RESOURCE_PROFILES,
        help="Filter by resource profile.",
    )
    parser.add_argument(
        "--determinism",
        choices=WORKLOAD_TAXONOMY_DETERMINISM,
        help="Filter by determinism class.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        choices=WORKLOAD_TAXONOMY_TAGS,
        help="Require a taxonomy tag (repeatable).",
    )
