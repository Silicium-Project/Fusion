"""Core types and helpers for coding style rules."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Iterable, List, Callable


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


@dataclass
class Rule:
    meta: RuleMeta
    severity: str
    kind: str
    spec: dict
    include: list[str]
    exclude: list[str]
    path_contains: list[str]

    def applies_to(self, rel_path) -> bool:  # PurePosixPath or similar
        if self.include and not _match_any(rel_path, self.include):
            return False
        if self.exclude and _match_any(rel_path, self.exclude):
            return False
        if self.path_contains:
            parts = rel_path.parts
            if not any(part in parts for part in self.path_contains):
                return False
        return True

    def check(self, rel_path, path: Path, content: str) -> List[Issue]:
        handler = _HANDLERS.get(self.kind)
        if not handler:
            raise ValueError(f"Unknown rule kind: {self.kind}")
        return handler(self, rel_path, path, content)


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


def _parse_scope(spec: dict) -> tuple[list[str], list[str], list[str]]:
    scope = spec.get("scope", {})
    include = list(scope.get("include", []))
    exclude = list(scope.get("exclude", []))
    path_contains = list(scope.get("path_contains", []))
    return include, exclude, path_contains


def _sanitize_content(rule: Rule, content: str) -> str:
    sanitize = rule.spec.get("sanitize", "none")
    if sanitize == "cpp":
        return sanitize_cpp(content)
    return content


def _compile_pattern(pattern: dict) -> re.Pattern:
    regex = pattern.get("regex")
    if not regex:
        raise ValueError("pattern.regex is required")
    return re.compile(regex)


def _pattern_label(pattern: dict) -> str:
    return pattern.get("label") or pattern.get("name") or "pattern"


def _check_pattern_count(rule: Rule, rel_path, path: Path, content: str) -> List[Issue]:
    text = _sanitize_content(rule, content)
    patterns = rule.spec.get("patterns", [])
    if not patterns:
        raise ValueError(f"Rule '{rule.meta.rule_id}' requires patterns")
    issues: List[Issue] = []
    for entry in patterns:
        regex = _compile_pattern(entry)
        matches = list(regex.finditer(text))
        min_count = int(entry.get("min", 0))
        max_count = int(entry.get("max", -1))
        label = _pattern_label(entry)
        if min_count > 0 and len(matches) < min_count:
            line, col = line_col_from_index(text, 0) if text else (1, 1)
            issues.append(
                Issue(
                    rule_id=rule.meta.rule_id,
                    message=f"Expected at least {min_count} {label}, found {len(matches)}.",
                    path=path,
                    line=line,
                    column=col,
                    severity=rule.severity,
                )
            )
        if max_count >= 0 and len(matches) > max_count:
            match = matches[max_count]
            line, col = line_col_from_index(text, match.start())
            issues.append(
                Issue(
                    rule_id=rule.meta.rule_id,
                    message=f"Expected at most {max_count} {label}, found {len(matches)}.",
                    path=path,
                    line=line,
                    column=col,
                    severity=rule.severity,
                )
            )
    return issues


def _check_pattern_match(rule: Rule, rel_path, path: Path, content: str) -> List[Issue]:
    text = _sanitize_content(rule, content)
    patterns = rule.spec.get("patterns", [])
    if not patterns:
        raise ValueError(f"Rule '{rule.meta.rule_id}' requires patterns")
    issues: List[Issue] = []
    for entry in patterns:
        regex = _compile_pattern(entry)
        message = entry.get("message") or f"Unsafe pattern detected: {_pattern_label(entry)}."
        for match in regex.finditer(text):
            line, col = line_col_from_index(text, match.start())
            issues.append(
                Issue(
                    rule_id=rule.meta.rule_id,
                    message=str(message),
                    path=path,
                    line=line,
                    column=col,
                    severity=rule.severity,
                )
            )
    return issues


def _check_cpp_primary_class_filename(rule: Rule, rel_path, path: Path, content: str) -> List[Issue]:
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
            rule_id=rule.meta.rule_id,
            message=f"Primary class/struct '{class_name}' does not match file name '{stem}'.",
            path=path,
            line=line,
            column=col,
            severity=rule.severity,
        )
    ]


def _check_cpp_header_source_pair(rule: Rule, rel_path, path: Path, content: str) -> List[Issue]:
    pairing = rule.spec.get("pairing", {})
    include_root = pairing.get("include_root", "include")
    src_root = pairing.get("src_root", "src")
    extensions = pairing.get("extensions", [".cpp", ".cc", ".cxx"])
    parts = list(rel_path.parts)
    if include_root not in parts:
        return []
    idx = parts.index(include_root)
    tail = parts[idx + 1 :]
    if not tail:
        return []
    stem = Path(tail[-1]).stem
    repo_root = path.parents[len(rel_path.parts) - 1]
    base_parts = parts[:idx] + [src_root] + tail[:-1]
    for ext in extensions:
        candidate = repo_root.joinpath(*base_parts, stem + ext)
        if candidate.exists():
            return []
    return [
        Issue(
            rule_id=rule.meta.rule_id,
            message=f"Missing source pair for header '{rel_path.as_posix()}'.",
            path=path,
            line=1,
            column=1,
            severity=rule.severity,
        )
    ]


def _check_cpp_include_order(rule: Rule, rel_path, path: Path, content: str) -> List[Issue]:
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
                    rule_id=rule.meta.rule_id,
                    message="Include order should be: <system/third-party> before \"project\".",
                    path=path,
                    line=idx,
                    column=1,
                    severity=rule.severity,
                )
            )
        else:
            current_group = group
    return issues


def _check_py_file_snake_case(rule: Rule, rel_path, path: Path, content: str) -> List[Issue]:
    stem = path.stem
    if stem in {"__init__", "__main__"}:
        return []
    if re.fullmatch(r"__\w+__", stem):
        return []
    if re.fullmatch(r"_*[a-z][a-z0-9_]*", stem):
        return []
    return [
        Issue(
            rule_id=rule.meta.rule_id,
            message=f"Python file name '{stem}' should be snake_case.",
            path=path,
            line=1,
            column=1,
            severity=rule.severity,
        )
    ]


def _check_py_function_snake_case(rule: Rule, rel_path, path: Path, content: str) -> List[Issue]:
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
                rule_id=rule.meta.rule_id,
                message=f"Function '{name}' should be snake_case.",
                path=path,
                line=idx,
                column=1,
                severity=rule.severity,
            )
        )
    return issues


def _check_py_final_constant_upper_snake(rule: Rule, rel_path, path: Path, content: str) -> List[Issue]:
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
                rule_id=rule.meta.rule_id,
                message=f"Constant '{name}' annotated with Final should be UPPER_SNAKE_CASE.",
                path=path,
                line=idx,
                column=1,
                severity=rule.severity,
            )
        )
    return issues


_HANDLERS: dict[str, Callable[[Rule, object, Path, str], List[Issue]]] = {
    "pattern_count": _check_pattern_count,
    "pattern_match": _check_pattern_match,
    "cpp_primary_class_filename": _check_cpp_primary_class_filename,
    "cpp_header_source_pair": _check_cpp_header_source_pair,
    "cpp_include_order": _check_cpp_include_order,
    "py_file_snake_case": _check_py_file_snake_case,
    "py_function_snake_case": _check_py_function_snake_case,
    "py_final_constant_upper_snake": _check_py_final_constant_upper_snake,
}


_DEFAULT_KIND_BY_ID = {
    "cpp.single_namespace_class": "pattern_count",
    "cpp.no_using_namespace_header": "pattern_count",
    "cpp.pragma_once_header": "pattern_count",
    "cpp.primary_class_filename": "cpp_primary_class_filename",
    "cpp.header_source_pair": "cpp_header_source_pair",
    "cpp.include_order": "cpp_include_order",
    "cpp.no_unsafe_allocation": "pattern_match",
    "py.file_snake_case": "py_file_snake_case",
    "py.function_snake_case": "py_function_snake_case",
    "py.final_constant_upper_snake": "py_final_constant_upper_snake",
}


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
    rule_id = spec.get("id")
    if not rule_id:
        raise ValueError("rule.id is required")
    kind = spec.get("kind") or _DEFAULT_KIND_BY_ID.get(rule_id)
    if not kind:
        raise ValueError(f"rule.kind is required for {rule_id}")
    include, exclude, path_contains = _parse_scope(spec)
    meta = RuleMeta(rule_id=rule_id, description=spec.get("description", ""))
    return Rule(
        meta=meta,
        severity=spec.get("severity", "error"),
        kind=kind,
        spec=spec,
        include=include,
        exclude=exclude,
        path_contains=path_contains,
    )


def load_rules_from_dir(path: Path) -> List[Rule]:
    if not path.exists():
        raise FileNotFoundError(f"Rules directory not found: {path}")
    if not path.is_dir():
        raise ValueError(f"Rules path is not a directory: {path}")
    rules: List[Rule] = []
    for file in sorted(path.glob("*.json")):
        rules.extend(load_rules_from_json(file))
    return rules
