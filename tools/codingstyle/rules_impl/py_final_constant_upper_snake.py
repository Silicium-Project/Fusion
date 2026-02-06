from __future__ import annotations

import re
from pathlib import Path

from tools.codingstyle.core import Issue, ScopedRule, re_python_final


class PyFinalConstantUpperRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "py.final_constant_upper_snake"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> list[Issue]:
        issues: list[Issue] = []
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
