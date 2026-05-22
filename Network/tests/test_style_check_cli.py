from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[1]
STYLE_CHECK_PATH = REPO_ROOT / "tools" / "style_check.py"


def _load_style_check_module():
    module_name = "style_check_cli_test"
    loader = SourceFileLoader(module_name, str(STYLE_CHECK_PATH))
    spec = importlib.util.spec_from_loader(module_name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


def _write_simple_rule(path: Path) -> None:
    payload = {
        "id": "cpp.no_unsafe_allocation",
        "kind": "pattern_match",
        "severity": "error",
        "scope": {"include": ["**/*.cpp"]},
        "patterns": [
            {
                "label": "new operator",
                "regex": r"\bnew\b",
                "message": "no raw new",
            }
        ],
        "sanitize": "cpp",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_style_check_changed_against_only_checks_changed_files(tmp_path: Path, monkeypatch) -> None:
    cli = _load_style_check_module()
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "good.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
    (src / "bad.cpp").write_text("int* p = new int(1);\n", encoding="utf-8")
    rules_file = tmp_path / "rules.json"
    _write_simple_rule(rules_file)

    monkeypatch.setattr(cli, "_git_changed_paths", lambda root, base, head: {PurePosixPath("src/good.cpp")})
    code = cli.main(
        [
            "--root",
            str(tmp_path),
            "--rules-file",
            str(rules_file),
            "--rules",
            "cpp.no_unsafe_allocation",
            "--changed-against",
            "HEAD~1",
        ]
    )

    assert code == 0


def test_style_check_changed_against_detects_issue_in_changed_file(tmp_path: Path, monkeypatch) -> None:
    cli = _load_style_check_module()
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "bad.cpp").write_text("int* p = new int(1);\n", encoding="utf-8")
    rules_file = tmp_path / "rules.json"
    _write_simple_rule(rules_file)

    monkeypatch.setattr(cli, "_git_changed_paths", lambda root, base, head: {PurePosixPath("src/bad.cpp")})
    code = cli.main(
        [
            "--root",
            str(tmp_path),
            "--rules-file",
            str(rules_file),
            "--rules",
            "cpp.no_unsafe_allocation",
            "--changed-against",
            "HEAD~1",
        ]
    )

    assert code == 1


def test_style_check_rejects_changed_against_with_path(tmp_path: Path) -> None:
    cli = _load_style_check_module()
    rules_file = tmp_path / "rules.json"
    _write_simple_rule(rules_file)
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "file.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")

    code = cli.main(
        [
            "--root",
            str(tmp_path),
            "--rules-file",
            str(rules_file),
            "--rules",
            "cpp.no_unsafe_allocation",
            "--changed-against",
            "HEAD~1",
            "--path",
            "src/file.cpp",
        ]
    )

    assert code == 2
