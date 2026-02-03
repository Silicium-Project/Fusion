"""Core types and helpers for coding style rules."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Iterable, List


@dataclass(frozen=True)
class Issue:
    rule_id: str
    message: str
    path: Path
    line: int
    column: int
    severity: str = "error"


@dataclass(frozen=True)
class RuleMeta:
    rule_id: str
    description: str


class Rule:
    meta: RuleMeta

    def applies_to(self, rel_path) -> bool:  # PurePosixPath or similar
        return True

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        raise NotImplementedError


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def register(self, rule: Rule) -> None:
        if rule.meta.rule_id in self._rules:
            raise ValueError(f"Duplicate rule id: {rule.meta.rule_id}")
        self._rules[rule.meta.rule_id] = rule

    def list_rules(self) -> List[RuleMeta]:
        return [rule.meta for rule in self._rules.values()]

    def resolve(self, rule_ids: Iterable[str] | None) -> List[Rule]:
        if not rule_ids:
            return list(self._rules.values())
        resolved: List[Rule] = []
        for rid in rule_ids:
            rule = self._rules.get(rid)
            if not rule:
                raise ValueError(f"Unknown rule id: {rid}")
            resolved.append(rule)
        return resolved


def sanitize_cpp(code: str) -> str:
    """Remove comments and strings while preserving line/column positions."""
    out: List[str] = []
    i = 0
    n = len(code)
    state = None
    raw_delim = ""

    def push(ch: str) -> None:
        out.append(ch)

    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""

        if state == "line_comment":
            if ch == "\n":
                state = None
                push(ch)
            else:
                push(" ")
            i += 1
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                push(" ")
                push(" ")
                i += 2
                state = None
            else:
                push("\n" if ch == "\n" else " ")
                i += 1
            continue
        if state == "string":
            if ch == "\\":
                push(" ")
                if i + 1 < n:
                    push(" ")
                    i += 2
                else:
                    i += 1
                continue
            if ch == '"':
                push(" ")
                i += 1
                state = None
            else:
                push("\n" if ch == "\n" else " ")
                i += 1
            continue
        if state == "char":
            if ch == "\\":
                push(" ")
                if i + 1 < n:
                    push(" ")
                    i += 2
                else:
                    i += 1
                continue
            if ch == "'":
                push(" ")
                i += 1
                state = None
            else:
                push("\n" if ch == "\n" else " ")
                i += 1
            continue
        if state == "raw_string":
            if code.startswith(")" + raw_delim + '"', i):
                for _ in range(len(raw_delim) + 2):
                    push(" ")
                i += len(raw_delim) + 2
                state = None
            else:
                push("\n" if ch == "\n" else " ")
                i += 1
            continue

        if ch == "/" and nxt == "/":
            push(" ")
            push(" ")
            i += 2
            state = "line_comment"
            continue
        if ch == "/" and nxt == "*":
            push(" ")
            push(" ")
            i += 2
            state = "block_comment"
            continue
        if ch == '"':
            push(" ")
            i += 1
            state = "string"
            continue
        if ch == "'":
            push(" ")
            i += 1
            state = "char"
            continue
        if ch == "R" and nxt == '"':
            j = i + 2
            delim = ""
            while j < n and code[j] != "(":
                delim += code[j]
                j += 1
            if j < n and code[j] == "(":
                push(" ")
                push(" ")
                for _ in delim:
                    push(" ")
                push(" ")
                i = j + 1
                state = "raw_string"
                raw_delim = delim
                continue
        push(ch)
        i += 1

    return "".join(out)


def line_col_from_index(text: str, index: int) -> tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    last_nl = text.rfind("\n", 0, index)
    if last_nl == -1:
        col = index + 1
    else:
        col = index - last_nl
    return line, col


def re_namespace() -> re.Pattern:
    return re.compile(r"\bnamespace\b\s*(?:[A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*)?\s*\{")


def re_class_or_struct() -> re.Pattern:
    return re.compile(r"\b(?<!enum\s)(class|struct)\s+[A-Za-z_]\w*\s*(?:final\s*)?(?:[^;{]*)\{")


def _match_any(rel_path, patterns: Iterable[str]) -> bool:
    return any(rel_path.match(pat) for pat in patterns)


def _internal_templates() -> dict[str, dict]:
    return {
        "cpp.single_namespace_class": {
            "sanitize": "cpp",
            "patterns": [
                {
                    "name": "namespace",
                    "label": "namespace declaration",
                    "regex": re_namespace(),
                    "default_max": 1,
                },
                {
                    "name": "class",
                    "label": "class/struct definition",
                    "regex": re_class_or_struct(),
                    "default_max": 1,
                },
            ],
        },
    }


class JsonRule(Rule):
    def __init__(self, spec: dict) -> None:
        rule_id = spec.get("id")
        if not rule_id:
            raise ValueError("rule.id is required")
        templates = _internal_templates()
        template = templates.get(rule_id)
        if not template:
            raise ValueError(f"No internal pattern template for rule id: {rule_id}")
        self.meta = RuleMeta(
            rule_id=rule_id,
            description=spec.get("description", ""),
        )
        self._sanitize = template.get("sanitize", "none")
        scope = spec.get("scope", {})
        self._include = list(scope.get("include", []))
        self._exclude = list(scope.get("exclude", []))
        self._path_contains = list(scope.get("path_contains", []))
        self._patterns: list[dict] = []
        limits = spec.get("limits", {})
        for entry in template.get("patterns", []):
            name = entry.get("name", "pattern")
            max_count = int(limits.get(name, entry.get("default_max", 0)))
            self._patterns.append(
                {
                    "name": name,
                    "label": entry.get("label", name),
                    "regex": entry["regex"],
                    "max": max_count,
                }
            )

    def applies_to(self, rel_path) -> bool:
        if self._include and not _match_any(rel_path, self._include):
            return False
        if self._exclude and _match_any(rel_path, self._exclude):
            return False
        if self._path_contains:
            parts = rel_path.parts
            if not any(part in parts for part in self._path_contains):
                return False
        return True

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        if self._sanitize == "cpp":
            text = sanitize_cpp(content)
        else:
            text = content
        issues: List[Issue] = []
        for pattern in self._patterns:
            matches = list(pattern["regex"].finditer(text))
            max_count = pattern["max"]
            if max_count >= 0 and len(matches) > max_count:
                match = matches[max_count]
                line, col = line_col_from_index(text, match.start())
                label = pattern["label"]
                issues.append(
                    Issue(
                        rule_id=self.meta.rule_id,
                        message=f"Expected at most {max_count} {label}, found {len(matches)}.",
                        path=path,
                        line=line,
                        column=col,
                    )
                )
        return issues


def load_rules_from_json(path: Path) -> List[Rule]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        rules = data
    elif isinstance(data, dict) and "rules" in data:
        rules = data.get("rules", [])
    elif isinstance(data, dict) and "id" in data:
        rules = [data]
    else:
        raise ValueError(f"Unsupported rules JSON in {path}")
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    return [JsonRule(spec) for spec in rules]


def load_rules_from_dir(path: Path) -> List[Rule]:
    if not path.exists():
        raise FileNotFoundError(f"Rules directory not found: {path}")
    if not path.is_dir():
        raise ValueError(f"Rules path is not a directory: {path}")
    rules: List[Rule] = []
    for file in sorted(path.glob("*.json")):
        rules.extend(load_rules_from_json(file))
    return rules
