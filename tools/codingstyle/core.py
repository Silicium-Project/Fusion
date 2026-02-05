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

def re_class_or_struct_name() -> re.Pattern:
    return re.compile(r"\b(?<!enum\s)(?:class|struct)\s+([A-Za-z_]\w*)\s*(?:final\s*)?(?:[^;{]*)\{")


def re_using_namespace() -> re.Pattern:
    return re.compile(r"\busing\s+namespace\s+[A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*\s*;")


def re_pragma_once() -> re.Pattern:
    return re.compile(r"^\s*#\s*pragma\s+once\b", re.MULTILINE)

def re_include_line() -> re.Pattern:
    return re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]')

def re_python_def() -> re.Pattern:
    return re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")

def re_python_final() -> re.Pattern:
    return re.compile(r"^\s*([A-Za-z_]\w*)\s*:\s*(?:typing\.)?Final\b")


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
        "cpp.no_using_namespace_header": {
            "sanitize": "cpp",
            "patterns": [
                {
                    "name": "using_namespace",
                    "label": "using namespace directive",
                    "regex": re_using_namespace(),
                    "default_max": 0,
                }
            ],
        },
        "cpp.pragma_once_header": {
            "sanitize": "cpp",
            "patterns": [
                {
                    "name": "pragma_once",
                    "label": "#pragma once",
                    "regex": re_pragma_once(),
                    "default_min": 1,
                    "default_max": 1,
                }
            ],
        },
    }


def _parse_scope(spec: dict) -> tuple[list[str], list[str], list[str]]:
    scope = spec.get("scope", {})
    include = list(scope.get("include", []))
    exclude = list(scope.get("exclude", []))
    path_contains = list(scope.get("path_contains", []))
    return include, exclude, path_contains


class ScopedRule(Rule):
    def __init__(self, spec: dict, *, rule_id: str, description: str) -> None:
        self.meta = RuleMeta(rule_id=rule_id, description=description)
        self._severity = spec.get("severity", "error")
        self._include, self._exclude, self._path_contains = _parse_scope(spec)

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


class CppPrimaryClassFilenameRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "cpp.primary_class_filename"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        text = sanitize_cpp(content)
        match = re_class_or_struct_name().search(text)
        if not match:
            return []
        class_name = match.group(1)
        stem = path.stem
        if stem == class_name:
            return []
        line, col = line_col_from_index(text, match.start(1))
        return [
            Issue(
                rule_id=self.meta.rule_id,
                message=f"Primary class/struct '{class_name}' does not match file name '{stem}'.",
                path=path,
                line=line,
                column=col,
                severity=self._severity,
            )
        ]


class CppHeaderSourcePairRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "cpp.header_source_pair"),
            description=spec.get("description", ""),
        )
        pairing = spec.get("pairing", {})
        self._include_root = pairing.get("include_root", "include")
        self._src_root = pairing.get("src_root", "src")
        self._extensions = pairing.get("extensions", [".cpp", ".cc", ".cxx"])

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        parts = list(rel_path.parts)
        if self._include_root not in parts:
            return []
        idx = parts.index(self._include_root)
        tail = parts[idx + 1 :]
        if not tail:
            return []
        stem = Path(tail[-1]).stem
        repo_root = path.parents[len(rel_path.parts) - 1]
        base_parts = parts[:idx] + [self._src_root] + tail[:-1]
        for ext in self._extensions:
            candidate = repo_root.joinpath(*base_parts, stem + ext)
            if candidate.exists():
                return []
        return [
            Issue(
                rule_id=self.meta.rule_id,
                message=f"Missing source pair for header '{rel_path.as_posix()}'.",
                path=path,
                line=1,
                column=1,
                severity=self._severity,
            )
        ]


class CppIncludeOrderRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "cpp.include_order"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        issues: List[Issue] = []
        include_re = re_include_line()
        current_group = -1
        for idx, line in enumerate(content.splitlines(), start=1):
            match = include_re.match(line)
            if not match:
                continue
            delimiter = match.group(1)
            group = 0 if delimiter == "<" else 1
            if group < current_group:
                issues.append(
                    Issue(
                        rule_id=self.meta.rule_id,
                        message="Include order should be: <system/third-party> before \"project\".",
                        path=path,
                        line=idx,
                        column=1,
                        severity=self._severity,
                    )
                )
            else:
                current_group = group
        return issues


class PyFileSnakeCaseRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "py.file_snake_case"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        stem = path.stem
        if stem in {"__init__", "__main__"}:
            return []
        if re.fullmatch(r"__\w+__", stem):
            return []
        if re.fullmatch(r"_*[a-z][a-z0-9_]*", stem):
            return []
        return [
            Issue(
                rule_id=self.meta.rule_id,
                message=f"Python file name '{stem}' should be snake_case.",
                path=path,
                line=1,
                column=1,
                severity=self._severity,
            )
        ]


class PyFunctionSnakeCaseRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "py.function_snake_case"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        issues: List[Issue] = []
        def_re = re_python_def()
        for idx, line in enumerate(content.splitlines(), start=1):
            match = def_re.match(line)
            if not match:
                continue
            name = match.group(1)
            if name.startswith("__") and name.endswith("__"):
                continue
            base = name.lstrip("_")
            if not base:
                continue
            if re.fullmatch(r"[a-z][a-z0-9_]*", base):
                continue
            issues.append(
                Issue(
                    rule_id=self.meta.rule_id,
                    message=f"Function '{name}' should be snake_case.",
                    path=path,
                    line=idx,
                    column=1,
                    severity=self._severity,
                )
            )
        return issues


class PyFinalConstantUpperRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "py.final_constant_upper_snake"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        issues: List[Issue] = []
        final_re = re_python_final()
        for idx, line in enumerate(content.splitlines(), start=1):
            match = final_re.match(line)
            if not match:
                continue
            name = match.group(1)
            if re.fullmatch(r"_?[A-Z][A-Z0-9_]*", name):
                continue
            issues.append(
                Issue(
                    rule_id=self.meta.rule_id,
                    message=f"Constant '{name}' annotated with Final should be UPPER_SNAKE_CASE.",
                    path=path,
                    line=idx,
                    column=1,
                    severity=self._severity,
                )
            )
        return issues


class CppUnsafePatternsRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "cpp.no_unsafe_allocation"),
            description=spec.get("description", ""),
        )
        self._patterns: list[dict[str, object]] = []
        for entry in spec.get("patterns", []):
            regex = entry.get("regex")
            if not regex:
                continue
            self._patterns.append(
                {
                    "regex": re.compile(regex),
                    "label": entry.get("label", regex),
                    "message": entry.get("message", ""),
                }
            )

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        text = sanitize_cpp(content)
        issues: List[Issue] = []
        for entry in self._patterns:
            regex = entry["regex"]
            for match in regex.finditer(text):
                line, col = line_col_from_index(text, match.start())
                message = entry.get("message") or f"Unsafe pattern detected: {entry.get('label')}."
                issues.append(
                    Issue(
                        rule_id=self.meta.rule_id,
                        message=str(message),
                        path=path,
                        line=line,
                        column=col,
                        severity=self._severity,
                    )
                )
        return issues


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
        self._severity = spec.get("severity", "error")
        self._sanitize = template.get("sanitize", "none")
        scope = spec.get("scope", {})
        self._include = list(scope.get("include", []))
        self._exclude = list(scope.get("exclude", []))
        self._path_contains = list(scope.get("path_contains", []))
        self._patterns: list[dict] = []
        limits = spec.get("limits", {})
        for entry in template.get("patterns", []):
            name = entry.get("name", "pattern")
            limit_spec = limits.get(name, None)
            default_min = int(entry.get("default_min", 0))
            default_max = int(entry.get("default_max", -1))
            if isinstance(limit_spec, dict):
                min_count = int(limit_spec.get("min", default_min))
                max_count = int(limit_spec.get("max", default_max))
            elif limit_spec is None:
                min_count = default_min
                max_count = default_max
            else:
                min_count = default_min
                max_count = int(limit_spec)
            self._patterns.append(
                {
                    "name": name,
                    "label": entry.get("label", name),
                    "regex": entry["regex"],
                    "max": max_count,
                    "min": min_count,
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
            min_count = pattern["min"]
            max_count = pattern["max"]
            if min_count > 0 and len(matches) < min_count:
                line = 1
                col = 1
                if text:
                    line, col = line_col_from_index(text, 0)
                label = pattern["label"]
                issues.append(
                    Issue(
                        rule_id=self.meta.rule_id,
                        message=f"Expected at least {min_count} {label}, found {len(matches)}.",
                        path=path,
                        line=line,
                        column=col,
                        severity=self._severity,
                    )
                )
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
                        severity=self._severity,
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
    return [_make_rule(spec) for spec in rules]


def _make_rule(spec: dict) -> Rule:
    rule_id = spec.get("id", "")
    custom = {
        "cpp.primary_class_filename": CppPrimaryClassFilenameRule,
        "cpp.header_source_pair": CppHeaderSourcePairRule,
        "cpp.include_order": CppIncludeOrderRule,
        "py.file_snake_case": PyFileSnakeCaseRule,
        "py.function_snake_case": PyFunctionSnakeCaseRule,
        "py.final_constant_upper_snake": PyFinalConstantUpperRule,
        "cpp.no_unsafe_allocation": CppUnsafePatternsRule,
    }
    rule_cls = custom.get(rule_id)
    if rule_cls:
        return rule_cls(spec)
    return JsonRule(spec)


def load_rules_from_dir(path: Path) -> List[Rule]:
    if not path.exists():
        raise FileNotFoundError(f"Rules directory not found: {path}")
    if not path.is_dir():
        raise ValueError(f"Rules path is not a directory: {path}")
    rules: List[Rule] = []
    for file in sorted(path.glob("*.json")):
        rules.extend(load_rules_from_json(file))
    return rules
