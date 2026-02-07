#!/usr/bin/env python3
"""General coding style checker with pluggable rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.codingstyle.core import Issue, RuleRegistry, load_rules_from_dir, load_rules_from_json

DEFAULT_INCLUDE = [
    "**/*.cpp",
    "**/*.hpp",
    "**/*.h",
    "**/*.cc",
    "**/*.cxx",
    "**/*.py",
]
DEFAULT_EXCLUDE = [
    ".git/**",
    "build/**",
    "dist/**",
    "out/**",
    ".venv/**",
    "node_modules/**",
    "docs/coverage/**",
]

def _match_any(rel_path: PurePosixPath, patterns: Iterable[str]) -> bool:
    return any(rel_path.match(pat) for pat in patterns)


def iter_files(root: Path, include: Iterable[str], exclude: Iterable[str]) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = PurePosixPath(path.relative_to(root).as_posix())
        if include and not _match_any(rel, include):
            continue
        if exclude and _match_any(rel, exclude):
            continue
        yield path


def load_config(path: Path | None) -> dict:
    if not path:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="General coding style checker")
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repo root (default: repo root)")
    parser.add_argument("--config", help="Optional JSON config file")
    parser.add_argument(
        "--rules-dir",
        default=str(REPO_ROOT / "tools" / "codingstyle" / "rules"),
        help="Rules directory (default: tools/codingstyle/rules)",
    )
    parser.add_argument(
        "--rules-file",
        help="Optional single rules JSON file (overrides --rules-dir)",
    )
    parser.add_argument("--include", action="append", default=[], help="Include glob (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], help="Exclude glob (repeatable)")
    parser.add_argument("--rules", action="append", default=[], help="Rule IDs to enable (repeatable)")
    parser.add_argument("--list-rules", action="store_true", help="List available rules")
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Treat warning severity as an error",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    registry = RuleRegistry()
    try:
        if args.rules_file:
            rules_file = Path(args.rules_file).resolve()
            for rule in load_rules_from_json(rules_file):
                registry.register(rule)
        else:
            rules_dir = Path(args.rules_dir).resolve()
            for rule in load_rules_from_dir(rules_dir):
                registry.register(rule)
    except Exception as exc:  # pragma: no cover - config errors
        print(f"Failed to load rules: {exc}", file=sys.stderr)
        return 2

    if args.list_rules:
        for meta in registry.list_rules():
            print(f"{meta.rule_id}: {meta.description}")
        return 0

    config = load_config(Path(args.config).resolve()) if args.config else {}
    include = args.include or config.get("include") or DEFAULT_INCLUDE
    exclude = args.exclude or config.get("exclude") or DEFAULT_EXCLUDE
    rule_ids = args.rules or config.get("rules") or []

    try:
        rules = registry.resolve(rule_ids)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    issues: List[Issue] = []
    for path in iter_files(root, include, exclude):
        rel = PurePosixPath(path.relative_to(root).as_posix())
        try:
            content = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            issues.append(
                Issue(
                    rule_id="core.read_error",
                    message=f"Failed to read file: {exc}",
                    path=path,
                    line=1,
                    column=1,
                    severity="error",
                )
            )
            continue
        for rule in rules:
            if not rule.applies_to(rel):
                continue
            issues.extend(rule.check(rel, path, content))

    if args.format == "json":
        payload = [
            {
                "rule": issue.rule_id,
                "message": issue.message,
                "path": str(issue.path),
                "line": issue.line,
                "column": issue.column,
                "severity": issue.severity,
            }
            for issue in issues
        ]
        print(json.dumps(payload, indent=2))
    else:
        for issue in issues:
            rel = issue.path.relative_to(root)
            color0 = "\033[36m"  # cyan for file path
            colorCol = "\033[32;1m"  # bright green for column number
            colorRow = "\033[35;1m"  # bright magenta for line number
            color1 = "\033[31m" if issue.severity == "error" else "\033[33m"  # red for error, yellow for warning
            color2 = "\033[34m"  # blue for rule ID
            color3 = "\033[30m"  # default for message
            clr = "\033[0m"
            print(f"{color0}{rel}{clr}:{colorRow}{issue.line}{clr}:{colorCol}{issue.column}{clr}: [{color1}{issue.severity.upper()}{clr}] {color2}{issue.rule_id}{clr} -> {color3}{issue.message}{clr}")

    if args.warnings_as_errors:
        has_errors = bool(issues)
    else:
        has_errors = any(issue.severity != "warning" for issue in issues)

    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
