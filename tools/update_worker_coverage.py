#!/usr/bin/env python3
"""Update the worker coverage snapshot in README.md from JSON summary.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
README_PATH = ROOT / "README.md"
SUMMARY_PATH = ROOT / "docs" / "coverage" / "worker" / "coverage-summary.json"


def load_summary(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(
            "Coverage summary not found. Push your branch and trigger the CI "
            "worker coverage pipeline (GitHub Actions `tests` workflow, job "
            "`worker-cpp`) to regenerate docs/coverage/worker/coverage-summary.json "
            "before refreshing the README."
        )

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def format_snapshot(summary: dict) -> str:
    line_percent = summary.get("line_percent")
    function_percent = summary.get("function_percent")
    branch_percent = summary.get("branch_percent")

    if not all(isinstance(v, (int, float)) for v in (line_percent, function_percent, branch_percent)):
        raise ValueError("Coverage summary is missing percentage fields")

    return (
        f"- Snapshot (auto) : lignes {line_percent:.1f} %, "
        f"fonctions {function_percent:.1f} %, branches {branch_percent:.1f} %"
    )


def update_readme(readme_path: Path, snapshot_line: str) -> None:
    content = readme_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(<!-- worker-coverage:start -->)\n.*?(<!-- worker-coverage:end -->)",
        re.DOTALL,
    )

    new_section = f"\\1\n{snapshot_line}\n\\2"
    new_content, count = pattern.subn(new_section, content)
    if count == 0:
        raise RuntimeError("Coverage markers not found in README.md")

    readme_path.write_text(new_content, encoding="utf-8")


def main() -> None:
    summary = load_summary(SUMMARY_PATH)
    snapshot_line = format_snapshot(summary)
    update_readme(README_PATH, snapshot_line)


if __name__ == "__main__":
    main()
