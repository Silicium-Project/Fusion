from __future__ import annotations

import re
from pathlib import Path

from tools.codingstyle.core import Issue, ScopedRule, line_col_from_index, sanitize_cpp


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

    def check(self, rel_path, path: Path, content: str) -> list[Issue]:
        text = sanitize_cpp(content)
        issues: list[Issue] = []
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
