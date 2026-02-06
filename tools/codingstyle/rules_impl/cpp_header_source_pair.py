from __future__ import annotations

from pathlib import Path

from tools.codingstyle.core import Issue, ScopedRule


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

    def check(self, rel_path, path: Path, content: str) -> list[Issue]:
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
