#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FixtureSpec:
    fixture_id: str
    filename: str
    description: str
    kind: str


FIXTURES: tuple[FixtureSpec, ...] = (
    FixtureSpec(
        fixture_id="valid-minimal-pe64",
        filename="valid-minimal-pe64.exe",
        description="Minimal PE32+ image with one section and no imports.",
        kind="valid",
    ),
    FixtureSpec(
        fixture_id="malformed-mz-only",
        filename="malformed-mz-only.exe",
        description="Malformed binary: MZ header without valid PE signature.",
        kind="malformed",
    ),
    FixtureSpec(
        fixture_id="unsupported-import-table-pe64",
        filename="unsupported-import-table-pe64.exe",
        description="Valid PE32+ header but with non-empty import table (unsupported path).",
        kind="unsupported_imports",
    ),
)


def _build_pe64(payload: bytes, *, with_import_table: bool) -> bytes:
    image_base = 0x140000000
    section_rva = 0x1000

    data = bytearray(0x200 + len(payload))
    data[0:2] = b"MZ"
    pe_offset = 0x80
    data[0x3C:0x40] = pe_offset.to_bytes(4, "little")
    data[pe_offset : pe_offset + 4] = b"PE\x00\x00"

    file_header = pe_offset + 4
    machine = 0x8664
    number_of_sections = 1
    optional_header_size = 0xF0
    characteristics = 0x0022
    data[file_header + 0 : file_header + 2] = machine.to_bytes(2, "little")
    data[file_header + 2 : file_header + 4] = number_of_sections.to_bytes(2, "little")
    data[file_header + 16 : file_header + 18] = optional_header_size.to_bytes(2, "little")
    data[file_header + 18 : file_header + 20] = characteristics.to_bytes(2, "little")

    optional = file_header + 20
    data[optional + 0 : optional + 2] = (0x20B).to_bytes(2, "little")  # PE32+
    data[optional + 16 : optional + 20] = section_rva.to_bytes(4, "little")
    data[optional + 24 : optional + 32] = image_base.to_bytes(8, "little")
    data[optional + 32 : optional + 36] = (0x1000).to_bytes(4, "little")  # section alignment
    data[optional + 36 : optional + 40] = (0x200).to_bytes(4, "little")  # file alignment
    data[optional + 56 : optional + 60] = (0x2000).to_bytes(4, "little")  # size of image
    data[optional + 60 : optional + 64] = (0x200).to_bytes(4, "little")  # size of headers
    data[optional + 108 : optional + 112] = (16).to_bytes(4, "little")  # number of directories
    if with_import_table:
        data[optional + 120 : optional + 124] = (0x1800).to_bytes(4, "little")
        data[optional + 124 : optional + 128] = (0x40).to_bytes(4, "little")

    section_header = optional + optional_header_size
    section_name = b".rdata\x00\x00"
    data[section_header + 0 : section_header + 8] = section_name
    data[section_header + 8 : section_header + 12] = len(payload).to_bytes(4, "little")
    data[section_header + 12 : section_header + 16] = section_rva.to_bytes(4, "little")
    data[section_header + 16 : section_header + 20] = len(payload).to_bytes(4, "little")
    data[section_header + 20 : section_header + 24] = (0x200).to_bytes(4, "little")
    data[section_header + 36 : section_header + 40] = (0x40000040).to_bytes(4, "little")

    data[0x200 : 0x200 + len(payload)] = payload
    return bytes(data)


def _build_fixture_bytes(kind: str) -> bytes:
    if kind == "valid":
        return _build_pe64(b"fixture-ok\x00", with_import_table=False)
    if kind == "malformed":
        data = bytearray(0x80)
        data[0:2] = b"MZ"
        return bytes(data)
    if kind == "unsupported_imports":
        return _build_pe64(b"x\x00", with_import_table=True)
    raise ValueError(f"Unsupported fixture kind: {kind}")


def build_corpus(repo_root: Path) -> None:
    out_dir = repo_root / "tests" / "fixtures" / "pe"
    out_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, object]] = []
    for spec in FIXTURES:
        data = _build_fixture_bytes(spec.kind)
        target = out_dir / spec.filename
        target.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        entries.append(
            {
                "id": spec.fixture_id,
                "filename": spec.filename,
                "kind": spec.kind,
                "description": spec.description,
                "size": len(data),
                "sha256": sha,
            }
        )

    manifest = {
        "schema_version": 1,
        "corpus_version": "v1",
        "generated_by": "tools/generate_pe_fixture_corpus.py",
        "entries": entries,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    build_corpus(repo_root)
    print("PE fixture corpus generated in tests/fixtures/pe/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
