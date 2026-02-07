from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_i18n_locale_report_strict() -> None:
    result = subprocess.run(
        [sys.executable, "tools/check_i18n_locales.py", "--strict", "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert "en-US" in report["locales"]
    assert "fr-FR" in report["locales"]
    for locale_name in report["locales"]:
        assert report["missing_keys"][locale_name] == []
        assert report["extra_keys"][locale_name] == []
        assert all(report["namespace_coverage"][locale_name].values())
