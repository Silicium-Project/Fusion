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
