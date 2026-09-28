"""`workload lint` and `workload fixtures`: manifest schema validation and
fixture integrity checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from tools.cli.constants import (
    WORKLOAD_FIXTURES_DIR,
    WORKLOAD_FIXTURES_INDEX,
    WORKLOAD_ROOT,
    WORKLOAD_SCHEMA_FILE,
)
from tools.cli.context import Context


def _schema_error_path(error: Any) -> str:
    path = getattr(error, "absolute_path", [])
    return "/".join(str(part) for part in path) or "<root>"


def lint_workload_manifests(root: Path, schema_path: Path) -> tuple[int, list[dict[str, str]]]:
    try:
        import yaml
    except ImportError:
        print("PyYAML is required for workload lint. Install with: python -m pip install pyyaml")
        sys.exit(1)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("jsonschema is required for workload lint. Install with: python -m pip install jsonschema")
        sys.exit(1)
    if not root.exists():
        print(f"Workload root not found: {root}")
        sys.exit(1)
    if not schema_path.exists():
        print(f"Workload schema not found: {schema_path}")
        sys.exit(1)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    manifests = sorted(root.rglob("manifest.yaml"))
    errors: list[dict[str, str]] = []

    for manifest_path in manifests:
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(
                {
                    "file": str(manifest_path),
                    "field": "<root>",
                    "rule": "yaml_parse",
                    "message": str(exc),
                }
            )
            continue

        if not isinstance(data, dict):
            errors.append(
                {
                    "file": str(manifest_path),
                    "field": "<root>",
                    "rule": "type",
                    "message": "manifest must be a YAML mapping",
                }
            )
            continue

        schema_errors = sorted(validator.iter_errors(data), key=lambda err: list(err.absolute_path))
        for error in schema_errors:
            errors.append(
                {
                    "file": str(manifest_path),
                    "field": _schema_error_path(error),
                    "rule": "schema_v1",
                    "message": error.message,
                }
            )

        relative = manifest_path.parent.relative_to(root)
        category = str(relative).replace("\\", "/").split("/", 1)[0]
        taxonomy = data.get("taxonomy", {})
        if isinstance(taxonomy, dict):
            taxonomy_category = taxonomy.get("category")
            if taxonomy_category is not None and taxonomy_category != category:
                errors.append(
                    {
                        "file": str(manifest_path),
                        "field": "taxonomy/category",
                        "rule": "taxonomy_category_match",
                        "message": f"expected '{category}', got '{taxonomy_category}'",
                    }
                )

    return len(manifests), errors


def cmd_workload_lint(args: argparse.Namespace, ctx: Context) -> None:
    root = Path(args.root).resolve()
    schema_path = Path(args.schema).resolve()
    checked, errors = lint_workload_manifests(root, schema_path)
    if args.json:
        print(
            json.dumps(
                {
                    "checked": checked,
                    "errors": errors,
                },
                indent=2,
            )
        )
    else:
        for error in errors:
            print(
                "[ERROR] "
                f"{error['file']} "
                f"field={error['field']} "
                f"rule={error['rule']} "
                f"message={error['message']}"
            )
        if errors:
            print(f"Validation failed: {len(errors)} error(s) across {checked} manifest(s).")
        else:
            print(f"All manifests valid: {checked} checked.")
    if errors:
        sys.exit(1)


def configure_workload_lint(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        default=str(WORKLOAD_ROOT),
        help="Workload root directory (default: catalog/workloads).",
    )
    parser.add_argument(
        "--schema",
        default=str(WORKLOAD_SCHEMA_FILE),
        help="Path to workload manifest schema JSON file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output lint report as JSON.",
    )


def _fixture_index() -> dict[str, Any]:
    if not WORKLOAD_FIXTURES_INDEX.exists():
        print(f"Fixture index not found: {WORKLOAD_FIXTURES_INDEX}")
        sys.exit(1)
    try:
        raw = json.loads(WORKLOAD_FIXTURES_INDEX.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to parse fixture index: {exc}")
        sys.exit(1)
    if not isinstance(raw, dict):
        print("Fixture index must be a JSON object.")
        sys.exit(1)
    return raw


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    normalize_text = path.suffix.lower() in {".json", ".txt", ".yaml", ".yml"}
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if normalize_text:
                chunk = chunk.replace(b"\r\n", b"\n")
            digest.update(chunk)
    return digest.hexdigest()


def _validate_fixtures(index: dict[str, Any]) -> dict[str, Any]:
    entries = index.get("entries", [])
    report = {
        "checked": 0,
        "passed": 0,
        "failed": 0,
        "errors": [],
    }
    if not isinstance(entries, list):
        report["errors"].append(
            {
                "fixture": "<index>",
                "field": "entries",
                "message": "entries must be a list",
            }
        )
        report["failed"] += 1
        return report

    for entry in entries:
        report["checked"] += 1
        if not isinstance(entry, dict):
            report["errors"].append(
                {"fixture": "<unknown>", "field": "<root>", "message": "entry must be object"}
            )
            report["failed"] += 1
            continue
        path = entry.get("path")
        fixture_id = entry.get("id", "<unknown>")
        sha_expected = entry.get("sha256")
        if not isinstance(path, str) or not path:
            report["errors"].append(
                {"fixture": fixture_id, "field": "path", "message": "path is required"}
            )
            report["failed"] += 1
            continue
        if not isinstance(sha_expected, str) or not sha_expected:
            report["errors"].append(
                {"fixture": fixture_id, "field": "sha256", "message": "sha256 is required"}
            )
            report["failed"] += 1
            continue
        fixture_path = WORKLOAD_FIXTURES_DIR / path
        if not fixture_path.exists():
            report["errors"].append(
                {
                    "fixture": fixture_id,
                    "field": "path",
                    "message": f"missing file: {fixture_path}",
                }
            )
            report["failed"] += 1
            continue
        actual = _sha256(fixture_path)
        if actual != sha_expected:
            report["errors"].append(
                {
                    "fixture": fixture_id,
                    "field": "sha256",
                    "message": f"hash mismatch for {path}",
                    "expected": sha_expected,
                    "actual": actual,
                }
            )
            report["failed"] += 1
            continue
        report["passed"] += 1
    return report


def cmd_workload_fixtures(args: argparse.Namespace, ctx: Context) -> None:
    index = _fixture_index()
    report = _validate_fixtures(index)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"Fixtures: {report['passed']} passed, "
            f"{report['failed']} failed, {report['checked']} checked."
        )
        for error in report["errors"]:
            fixture = error.get("fixture", "<unknown>")
            field = error.get("field", "<root>")
            message = error.get("message", "error")
            print(f"[ERROR] {fixture} field={field} message={message}")
    if report["failed"] > 0:
        sys.exit(1)


def configure_workload_fixtures(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output fixture integrity report as JSON.",
    )
