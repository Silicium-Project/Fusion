from pathlib import Path

from tools.dev.quality.check_utf8 import check_utf8


def test_repo_files_are_utf8():
    root = Path(__file__).resolve().parent.parent
    failures = check_utf8(root)
    assert not failures, "\n".join(failures)


def test_generated_anchor_artifacts_are_excluded(tmp_path):
    generated = tmp_path / ".anchor" / "test-ledger"
    generated.mkdir(parents=True)
    (generated / "runtime-artifact").write_bytes(b"\xff\xfe")

    assert check_utf8(tmp_path) == []


def test_generated_rust_e2e_binary_state_is_excluded(tmp_path):
    generated = tmp_path / "target" / "e2e" / "sha256" / "o"
    generated.mkdir(parents=True)
    (generated / "identity.key").write_bytes(b"\xff\xfe")
    assert check_utf8(tmp_path) == []


def test_invalid_utf8_in_maintained_sources_still_fails(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.rs").write_bytes(b"\xff\xfe")
    failures = check_utf8(tmp_path)
    assert len(failures) == 1
    assert "main.rs" in failures[0]
