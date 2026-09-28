from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SILICIUM = REPO_ROOT / "silicium"
SCHEMA = REPO_ROOT / "workloads" / "schema" / "workload-manifest-v2.schema.json"


def _run_lint(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SILICIUM), "workload", "lint", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_workload_lint_passes_repo_catalog() -> None:
    result = _run_lint()
    assert result.returncode == 0, result.stderr
    assert "All manifests valid:" in result.stdout


def test_workload_lint_reports_schema_violation(tmp_path: Path) -> None:
    # Missing taxonomy block triggers schema required-field violation.
    root = tmp_path / "workloads"
    manifest = root / "calcul" / "demo" / "task" / "manifest.yaml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        "\n".join(
            [
                "schema_version: 2",
                "id: calcul/demo/task",
                "version: 0.1.0",
                "runtime:",
                "  kind: planned",
                "engine: python",
                "command: python task.py",
                "resources:",
                "  cpu: 1",
                "  gpu: none",
                "  memory: 1Gi",
                "artifacts:",
                "  input:",
                "    - name: in",
                "      type: text/plain",
                "  output:",
                "    - name: out",
                "      type: text/plain",
                "validation:",
                "  policy: test",
                "payment:",
                "  unit: batch",
                "  estimated_cost: 0.1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_lint("--root", str(root), "--schema", str(SCHEMA))
    assert result.returncode == 1
    assert "field=<root>" in result.stdout
    assert "rule=schema " in result.stdout
    assert "taxonomy" in result.stdout


def test_workload_lint_json_output() -> None:
    result = _run_lint("--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "checked" in payload
    assert "errors" in payload
    assert payload["errors"] == []


def _write_valid_manifest(root: Path, folder: str, manifest_id: str, handler: str | None) -> None:
    source = (REPO_ROOT / "workloads" / "calcul" / "libm" / "sin" / "manifest.yaml").read_text(encoding="utf-8")
    source = source.replace("id: calcul/libm/sin", f"id: {manifest_id}", 1)
    if handler is not None:
        source = source.replace("handler: workloads.standard.handlers:libm", f"handler: {handler}", 1)
    target = root / folder / "manifest.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def test_workload_lint_requires_id_to_match_folder(tmp_path: Path) -> None:
    root = tmp_path / "workloads"
    _write_valid_manifest(root, "calcul/demo/other-name", "calcul/demo/task", None)
    result = _run_lint("--root", str(root), "--schema", str(SCHEMA))
    assert result.returncode == 1
    assert "id_matches_folder" in result.stdout


def test_workload_lint_requires_an_importable_handler(tmp_path: Path) -> None:
    root = tmp_path / "workloads"
    _write_valid_manifest(root, "calcul/demo/task", "calcul/demo/task", "workloads.standard.handlers:missing")
    result = _run_lint("--root", str(root), "--schema", str(SCHEMA))
    assert result.returncode == 1
    assert "handler_importable" in result.stdout
