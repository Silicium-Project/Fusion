from __future__ import annotations

from pathlib import Path

from tools.codingstyle.core import Issue, ScopedRule, re_include_line


class CppIncludeOrderRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "cpp.include_order"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> list[Issue]:
        issues: list[Issue] = []
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
