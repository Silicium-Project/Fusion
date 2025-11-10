from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_ROOT = REPO_ROOT / "catalog" / "workloads"
MANIFEST_FILES = sorted(MANIFEST_ROOT.rglob("manifest.yaml"))

REQUIRED_TOP_LEVEL = {
    "id",
    "version",
    "engine",
    "command",
    "resources",
    "artifacts",
    "validation",
    "payment",
}
REQUIRED_RESOURCE_FIELDS = {"cpu", "gpu", "memory"}
REQUIRED_PAYMENT_FIELDS = {"unit", "estimated_cost"}
ARTIFACT_GROUPS = ("input", "output")


@pytest.mark.parametrize(
    "manifest_path",
    MANIFEST_FILES,
    ids=lambda path: str(path.relative_to(MANIFEST_ROOT)),
)
def test_manifest_schema(manifest_path: Path) -> None:
    data = yaml.safe_load(manifest_path.read_text())
    assert isinstance(data, dict), f"{manifest_path} must contain a mapping"

    missing = REQUIRED_TOP_LEVEL - data.keys()
    assert not missing, f"{manifest_path} missing keys: {sorted(missing)}"

    relative_parent = manifest_path.parent.relative_to(MANIFEST_ROOT)
    assert str(relative_parent).replace("\\", "/") in data["id"], (
        f"{manifest_path} id should contain its folder name ({relative_parent})"
    )

    resources = data["resources"]
    assert isinstance(resources, dict), f"{manifest_path} resources must be a mapping"
    for field in REQUIRED_RESOURCE_FIELDS:
        assert field in resources, f"{manifest_path} resources missing '{field}'"
        if field == "memory" or field == "gpu":
            assert isinstance(
                resources[field], str
            ), f"{manifest_path} resources.{field} must be a string"
        else:
            assert isinstance(
                resources[field], (int, float)
            ), f"{manifest_path} resources.{field} must be numeric"

    artifacts = data["artifacts"]
    assert isinstance(artifacts, dict), f"{manifest_path} artifacts must be a mapping"
    for group in ARTIFACT_GROUPS:
        assert group in artifacts, f"{manifest_path} artifacts missing '{group}'"
        assert isinstance(
            artifacts[group], list
        ), f"{manifest_path} artifacts.{group} must be a list"
        assert artifacts[group], f"{manifest_path} artifacts.{group} must not be empty"
        for entry in artifacts[group]:
            assert isinstance(entry, dict), "artifact entries must be mappings"
            for leaf in ("name", "type"):
                assert leaf in entry, f"artifact entry missing '{leaf}'"

    validation = data["validation"]
    assert isinstance(validation, dict), f"{manifest_path} validation must be a mapping"
    assert validation, f"{manifest_path} validation block must not be empty"

    payment = data["payment"]
    assert isinstance(payment, dict), f"{manifest_path} payment must be a mapping"
    for field in REQUIRED_PAYMENT_FIELDS:
        assert field in payment, f"{manifest_path} payment missing '{field}'"
    assert isinstance(
        payment["estimated_cost"], (int, float)
    ), f"{manifest_path} payment.estimated_cost must be numeric"
    assert payment["estimated_cost"] > 0, f"{manifest_path} estimated_cost must be > 0"
