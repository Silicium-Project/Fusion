from __future__ import annotations

import re
from pathlib import Path

from tools.codingstyle.core import Issue, ScopedRule, re_python_def


class PyFunctionSnakeCaseRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "py.function_snake_case"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> list[Issue]:
        issues: list[Issue] = []
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
