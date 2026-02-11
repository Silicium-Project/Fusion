from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "tests" / "fixtures" / "pe"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"


def _parse_pe(data: bytes) -> tuple[bool, bool]:
    if len(data) < 0x40 or data[:2] != b"MZ":
        return False, False

    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    if pe_offset + 4 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        return False, False

    optional = pe_offset + 24
    if optional + 128 > len(data):
        return True, False

    number_of_rva_and_sizes = int.from_bytes(data[optional + 108 : optional + 112], "little")
    if number_of_rva_and_sizes <= 1:
        return True, False

    import_rva = int.from_bytes(data[optional + 120 : optional + 124], "little")
    import_size = int.from_bytes(data[optional + 124 : optional + 128], "little")
    return True, import_rva != 0 and import_size != 0


def test_pe_fixture_manifest_and_hashes() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["corpus_version"] == "v1"

    entries = manifest["entries"]
    assert isinstance(entries, list)
    assert len(entries) == 3

    kinds = {entry["kind"] for entry in entries}
    assert kinds == {"valid", "malformed", "unsupported_imports"}

    for entry in entries:
        fixture_path = CORPUS_DIR / entry["filename"]
        data = fixture_path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["size"]


def test_pe_fixture_semantics() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_kind = {entry["kind"]: entry for entry in manifest["entries"]}

    valid_data = (CORPUS_DIR / by_kind["valid"]["filename"]).read_bytes()
    malformed_data = (CORPUS_DIR / by_kind["malformed"]["filename"]).read_bytes()
    unsupported_data = (CORPUS_DIR / by_kind["unsupported_imports"]["filename"]).read_bytes()

    valid_is_pe, valid_has_imports = _parse_pe(valid_data)
    malformed_is_pe, malformed_has_imports = _parse_pe(malformed_data)
    unsupported_is_pe, unsupported_has_imports = _parse_pe(unsupported_data)

    assert valid_is_pe is True
    assert valid_has_imports is False
    assert malformed_is_pe is False
    assert malformed_has_imports is False
    assert unsupported_is_pe is True
    assert unsupported_has_imports is True
