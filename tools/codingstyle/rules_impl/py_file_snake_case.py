from __future__ import annotations

import re
from pathlib import Path

from tools.codingstyle.core import Issue, ScopedRule


class PyFileSnakeCaseRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "py.file_snake_case"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> list[Issue]:
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
