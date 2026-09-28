#!/usr/bin/env python3
"""CI check: reject user-facing strings that bypass the i18n catalog."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_PATHS = [
    "silicium",
    "tools/dev/tui",
    "infra",
    "networked",
    "workloads",
]

DEFAULT_EXCLUDES = (
    "tests/",
    "docs/",
    "i18n/locales/",
    "tools/dev/quality/check_i18n_hardcoded_strings.py",
)

STRING_LITERAL_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')
KEY_LIKE_RE = re.compile(r"^[a-z0-9_.:/-]+$")
WORD_RE = re.compile(r"[A-Za-z]")


def _run_git_diff(base: str, head: str, paths: list[str]) -> str:
    cmd = ["git", "diff", "--no-color", "--unified=0", base, head, "--", *paths]
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=60, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return result.stdout


def _resolve_base(base: str | None) -> str | None:
    if base:
        check = subprocess.run(
            ["git", "rev-parse", "--verify", base],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        return base if check.returncode == 0 else None
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD~1"],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    return "HEAD~1" if probe.returncode == 0 else None


def _load_exceptions(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("exceptions file must be a JSON list")
    parsed: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path_regex = item.get("path_regex")
        literal_regex = item.get("literal_regex")
        reason = item.get("reason", "")
        if isinstance(path_regex, str) and isinstance(literal_regex, str):
            parsed.append(
                {
                    "path_regex": path_regex,
                    "literal_regex": literal_regex,
                    "reason": reason if isinstance(reason, str) else "",
                }
            )
    return parsed


def _literal_content(raw_literal: str) -> str:
    if len(raw_literal) < 2:
        return raw_literal
    quote = raw_literal[0]
    if quote not in ("'", '"') or raw_literal[-1] != quote:
        return raw_literal
    return raw_literal[1:-1]


def _looks_user_facing(content: str) -> bool:
    if len(content.strip()) < 4:
        return False
    if not WORD_RE.search(content):
        return False
    if KEY_LIKE_RE.fullmatch(content):
        return False
    if content.startswith("--") or content.startswith("-"):
        return False
    if "\\" in content or "/" in content:
        return False
    has_space = " " in content
    sentence_like = any(ch in content for ch in (".", ":", "!", "?"))
    title_like = content[:1].isupper() and len(content) > 8
    return has_space or sentence_like or title_like


def _is_exception(
    file_path: str, literal: str, exceptions: list[dict[str, str]]
) -> tuple[bool, str]:
    for item in exceptions:
        if re.search(item["path_regex"], file_path) and re.search(item["literal_regex"], literal):
            return True, item.get("reason", "")
    return False, ""


def parse_added_lines(diff_text: str) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    current_file: str | None = None
    new_line = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if line.startswith("@@ "):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                new_line = int(match.group(1))
            continue
        if not current_file:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            content_line = line[1:]
            if "i18n:ignore" in content_line:
                new_line += 1
                continue
            for match in STRING_LITERAL_RE.finditer(content_line):
                raw = match.group(0)
                if not raw:
                    continue
                content = _literal_content(raw)
                if _looks_user_facing(content):
                    violations.append(
                        {
                            "file": current_file,
                            "line": new_line,
                            "literal": content,
                            "source": content_line.strip(),
                        }
                    )
            new_line += 1
            continue
        if line.startswith("-") and not line.startswith("---"):
            continue
        if line.startswith(" "):
            new_line += 1
    return violations


def filter_violations(
    violations: list[dict[str, Any]],
    exceptions: list[dict[str, str]],
    excludes: tuple[str, ...],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in violations:
        file_path = str(item["file"])
        if any(file_path.startswith(prefix) for prefix in excludes):
            continue
        exempt, reason = _is_exception(file_path, str(item["literal"]), exceptions)
        if exempt:
            continue
        if reason:
            item["reason"] = reason
        filtered.append(item)
    return filtered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect newly introduced hard-coded user-facing strings."
    )
    parser.add_argument("--base", help="Base ref for git diff (default HEAD~1 when available).")
    parser.add_argument("--head", default="HEAD", help="Head ref for git diff.")
    parser.add_argument("--json", action="store_true", help="Output JSON report.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on violations.")
    parser.add_argument("--diff-file", help="Read unified diff from file (test mode).")
    parser.add_argument(
        "--exceptions",
        default="docs/i18n/hardcoded-exceptions.json",
        help="JSON file containing approved exceptions.",
    )
    args = parser.parse_args()

    exceptions = _load_exceptions(Path(args.exceptions))
    if args.diff_file:
        diff_text = Path(args.diff_file).read_text(encoding="utf-8")
    else:
        base = _resolve_base(args.base)
        if not base:
            report = {"base": None, "head": args.head, "checked": 0, "violations": []}
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print("No valid base ref; hardcoded-string check skipped.")
            return
        diff_text = _run_git_diff(base, args.head, DEFAULT_PATHS)

    violations = parse_added_lines(diff_text)
    violations = filter_violations(violations, exceptions, DEFAULT_EXCLUDES)
    report = {"checked": len(violations), "violations": violations}

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        if not violations:
            print("No hard-coded user-facing strings detected.")
        else:
            print(f"Detected {len(violations)} hard-coded user-facing string(s):")
            for item in violations:
                print(
                    f"- {item['file']}:{item['line']} literal={item['literal']!r} "
                    f"source={item['source']}"
                )
            print("Use i18n keys or add explicit suppression with 'i18n:ignore'.")

    if args.strict and violations:
        sys.exit(1)


if __name__ == "__main__":
    main()
