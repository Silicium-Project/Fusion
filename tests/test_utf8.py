from pathlib import Path

from tools.check_utf8 import check_utf8


def test_repo_files_are_utf8():
    root = Path(__file__).resolve().parent.parent
    failures = check_utf8(root)
    assert not failures, "\n".join(failures)
