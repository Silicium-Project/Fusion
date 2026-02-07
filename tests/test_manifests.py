from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_ROOT = REPO_ROOT / "catalog" / "workloads"
SCHEMA_PATH = REPO_ROOT / "catalog" / "workloads" / "schema" / "workload-manifest-v1.schema.json"
MANIFEST_FILES = sorted(MANIFEST_ROOT.rglob("manifest.yaml"))
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def _format_schema_error(error: ValidationError) -> str:
    path = "/".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{path}: {error.message}"


@pytest.mark.parametrize(
    "manifest_path",
    MANIFEST_FILES,
    ids=lambda path: str(path.relative_to(MANIFEST_ROOT)),
)
def test_manifest_schema(manifest_path: Path) -> None:
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{manifest_path} must contain a mapping"

    errors = sorted(VALIDATOR.iter_errors(data), key=lambda err: list(err.absolute_path))
    assert not errors, (
        f"{manifest_path} failed schema validation:\n"
        + "\n".join(f"- {_format_schema_error(err)}" for err in errors)
    )

    relative_parent = manifest_path.parent.relative_to(MANIFEST_ROOT)
    assert str(relative_parent).replace("\\", "/") in data["id"], (
        f"{manifest_path} id should contain its folder name ({relative_parent})"
    )
