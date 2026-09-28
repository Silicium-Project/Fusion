from __future__ import annotations

import json
from pathlib import Path
from tools.dev.release import generate_update_manifest
from tools.network_node import NodeIdentity, stable_json


def test_create_signed_update_manifest(tmp_path: Path) -> None:
    artifact = tmp_path / "release.tar.gz"
    artifact.write_bytes(b"dummy release payload")

    config = generate_update_manifest.build_default_config(tmp_path)
    identity = NodeIdentity(config)
    manifest = generate_update_manifest.create_signed_update_manifest(
        channel="dev",
        version="0.3.0",
        artifact_path=artifact,
        artifact_url="http://download.silicium.network/dev/release.tar.gz",
        identity=identity,
    )

    assert manifest["channel"] == "dev"
    assert manifest["version"] == "0.3.0"
    assert manifest["size_bytes"] == len(b"dummy release payload")
    assert manifest["publisher_id"] == identity.identity_id

    # Verify signature
    unsigned = {
        key: value
        for key, value in manifest.items()
        if key != "signature"
    }
    msg = stable_json(unsigned).encode("utf-8")
    assert NodeIdentity.verify_bytes(msg, manifest["signature"], identity.public_key_b64) is True
