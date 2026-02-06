from __future__ import annotations

from pathlib import Path

from tools.codingstyle.core import Issue, ScopedRule, line_col_from_index, re_class_or_struct_name, sanitize_cpp


class CppPrimaryClassFilenameRule(ScopedRule):
    def __init__(self, spec: dict) -> None:
        super().__init__(
            spec,
            rule_id=spec.get("id", "cpp.primary_class_filename"),
            description=spec.get("description", ""),
        )

    def check(self, rel_path, path: Path, content: str) -> list[Issue]:
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
