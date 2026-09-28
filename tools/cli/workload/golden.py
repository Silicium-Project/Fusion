"""`workload alignment` and `workload golden`: family alignment policy and
golden corpus checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from tools.cli.constants import WORKLOAD_ALIGNMENT_POLICY, WORKLOAD_GOLDEN_CORPUS_FILE, WORKLOAD_ROOT
from tools.cli.context import Context
from tools.cli.workload.lint import _fixture_index
from tools.cli.workload.manifest import _workload_dry_run_plan, _workload_entries


def _workload_family_from_id(workload_id: str) -> str:
    parts = workload_id.split("/")
    if len(parts) < 2:
        return workload_id
    return "/".join(parts[:2])


def _alignment_policy() -> dict[str, Any]:
    if not WORKLOAD_ALIGNMENT_POLICY.exists():
        return {"schema_version": 1, "critical_families": []}
    try:
        raw = json.loads(WORKLOAD_ALIGNMENT_POLICY.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to parse alignment policy: {exc}")
        sys.exit(1)
    if not isinstance(raw, dict):
        print("Alignment policy must be a JSON object.")
        sys.exit(1)
    return raw


def workload_alignment_report() -> dict[str, Any]:
    entries = _workload_entries()
    manifest_ids: list[str] = []
    for _, data in entries:
        workload_id = data.get("id")
        if isinstance(workload_id, str) and workload_id:
            manifest_ids.append(workload_id)
    families = sorted({_workload_family_from_id(workload_id) for workload_id in manifest_ids})

    fixture_index = _fixture_index()
    fixture_entries = fixture_index.get("entries", [])
    fixture_ids: list[str] = []
    if isinstance(fixture_entries, list):
        for entry in fixture_entries:
            if isinstance(entry, dict):
                fixture_id = entry.get("id")
                if isinstance(fixture_id, str) and fixture_id:
                    fixture_ids.append(fixture_id)

    covered_families = sorted({_workload_family_from_id(fixture_id) for fixture_id in fixture_ids})
    missing_families = sorted(set(families) - set(covered_families))

    policy = _alignment_policy()
    critical = policy.get("critical_families", [])
    critical_families = [value for value in critical if isinstance(value, str) and value]
    critical_missing = sorted(set(critical_families).intersection(set(missing_families)))

    return {
        "total_workloads": len(manifest_ids),
        "total_families": len(families),
        "families": families,
        "families_with_fixtures": covered_families,
        "missing_families": missing_families,
        "critical_families": sorted(critical_families),
        "critical_missing_families": critical_missing,
        "fixture_entries": len(fixture_ids),
    }


def cmd_workload_alignment(args: argparse.Namespace, ctx: Context) -> None:
    report = workload_alignment_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"Workload alignment: {report['total_families'] - len(report['missing_families'])}/"
            f"{report['total_families']} families covered by fixtures."
        )
        if report["missing_families"]:
            print("Missing families:")
            for family in report["missing_families"]:
                print(f"  - {family}")
        else:
            print("No missing families.")
        if report["critical_missing_families"]:
            print("Critical missing families:")
            for family in report["critical_missing_families"]:
                print(f"  - {family}")
    if args.strict and report["critical_missing_families"]:
        sys.exit(1)


def configure_workload_alignment(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output alignment report as JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when critical families are missing fixture coverage.",
    )


def _golden_corpus(path: Path) -> dict[str, Any]:
    if not path.exists():
        print(f"Golden corpus not found: {path}")
        sys.exit(1)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to parse golden corpus: {exc}")
        sys.exit(1)
    if not isinstance(raw, dict):
        print("Golden corpus must be a JSON object.")
        sys.exit(1)
    return raw


def _golden_case_hash(plan: dict[str, Any], manifest_data: dict[str, Any]) -> str:
    material = {
        "engine": manifest_data.get("engine"),
        "command": plan.get("command"),
        "artifacts": manifest_data.get("artifacts", {}),
        "preset": plan.get("preset"),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def workload_golden_report(corpus_path: Path) -> dict[str, Any]:
    corpus = _golden_corpus(corpus_path)
    cases = corpus.get("cases", [])
    report: dict[str, Any] = {
        "checked": 0,
        "passed": 0,
        "failed": 0,
        "errors": [],
    }
    if not isinstance(cases, list):
        report["errors"].append(
            {"case": "<corpus>", "field": "cases", "message": "cases must be a list"}
        )
        report["failed"] += 1
        return report

    entries = _workload_entries()
    by_id: dict[str, tuple[str, dict[str, Any]]] = {}
    for path, data in entries:
        workload_id = data.get("id")
        if isinstance(workload_id, str) and workload_id:
            by_id[workload_id] = (path, data)

    for case in cases:
        report["checked"] += 1
        if not isinstance(case, dict):
            report["failed"] += 1
            report["errors"].append(
                {"case": "<unknown>", "field": "<root>", "message": "case must be object"}
            )
            continue
        workload_id = case.get("id")
        preset = case.get("preset")
        expected_hash = case.get("expected_plan_hash")
        case_name = str(workload_id) if workload_id else "<unknown>"
        if not isinstance(workload_id, str) or not workload_id:
            report["failed"] += 1
            report["errors"].append(
                {"case": case_name, "field": "id", "message": "id is required"}
            )
            continue
        if not isinstance(expected_hash, str) or not expected_hash:
            report["failed"] += 1
            report["errors"].append(
                {
                    "case": case_name,
                    "field": "expected_plan_hash",
                    "message": "expected_plan_hash is required",
                }
            )
            continue
        if workload_id not in by_id:
            report["failed"] += 1
            report["errors"].append(
                {
                    "case": case_name,
                    "field": "id",
                    "message": f"workload id not found: {workload_id}",
                }
            )
            continue

        path, manifest_data = by_id[workload_id]
        taxonomy = manifest_data.get("taxonomy", {})
        determinism = taxonomy.get("determinism") if isinstance(taxonomy, dict) else None
        if determinism != "deterministic":
            report["failed"] += 1
            report["errors"].append(
                {
                    "case": case_name,
                    "field": "taxonomy.determinism",
                    "message": f"golden corpus requires deterministic workload, got {determinism}",
                }
            )
            continue

        manifest_path = WORKLOAD_ROOT / path / "manifest.yaml"
        plan = _workload_dry_run_plan(
            path,
            manifest_path,
            manifest_data,
            preset if isinstance(preset, str) else None,
        )
        missing = plan.get("missing_variables", [])
        if isinstance(missing, list) and missing:
            report["failed"] += 1
            report["errors"].append(
                {
                    "case": case_name,
                    "field": "missing_variables",
                    "message": f"missing variables: {', '.join(str(value) for value in missing)}",
                }
            )
            continue
        actual_hash = _golden_case_hash(plan, manifest_data)
        if actual_hash != expected_hash:
            report["failed"] += 1
            report["errors"].append(
                {
                    "case": case_name,
                    "field": "expected_plan_hash",
                    "message": "plan hash mismatch",
                    "expected": expected_hash,
                    "actual": actual_hash,
                }
            )
            continue
        report["passed"] += 1
    return report


def cmd_workload_golden(args: argparse.Namespace, ctx: Context) -> None:
    corpus_path = Path(args.corpus).resolve()
    report = workload_golden_report(corpus_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"Golden corpus: {report['passed']} passed, "
            f"{report['failed']} failed, {report['checked']} checked."
        )
        for error in report["errors"]:
            case = error.get("case", "<unknown>")
            field = error.get("field", "<root>")
            message = error.get("message", "error")
            print(f"[ERROR] {case} field={field} message={message}")
    if args.strict and report["failed"] > 0:
        sys.exit(1)


def configure_workload_golden(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--corpus",
        default=str(WORKLOAD_GOLDEN_CORPUS_FILE),
        help="Path to golden corpus JSON file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output golden validation report as JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any golden case check fails.",
    )
