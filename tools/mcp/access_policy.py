"""Allow/deny lists for MCP tools and resources.

Rules are matched against tool names or resource URIs:

- ``prefix*``         matches anything starting with ``prefix``;
- ``.../{task_id}``   matches anything starting with the part before ``{task_id}``;
- anything else       must match exactly.

The deny list always wins; an empty allow list allows everything.
"""

from __future__ import annotations


def policy_rule_matches(value: str, rule: str) -> bool:
    """Return True when ``value`` matches one allow/deny ``rule``."""
    r = rule.strip()
    if not r:
        return False
    if r.endswith("*"):
        return value.startswith(r[:-1])
    if "{task_id}" in r:
        return value.startswith(r.split("{task_id}", 1)[0])
    return value == r


def _matches_any(value: str, rules: tuple[str, ...]) -> bool:
    return any(policy_rule_matches(value, rule) for rule in rules)


class McpAccessPolicy:
    """Decides which tools and resources a server instance exposes."""

    def __init__(
        self,
        *,
        tool_allowlist: list[str] | None = None,
        tool_denylist: list[str] | None = None,
        resource_allowlist: list[str] | None = None,
        resource_denylist: list[str] | None = None,
    ) -> None:
        self._tool_allowlist = tuple(tool_allowlist or [])
        self._tool_denylist = tuple(tool_denylist or [])
        self._resource_allowlist = tuple(resource_allowlist or [])
        self._resource_denylist = tuple(resource_denylist or [])

    def tool_allowed(self, name: str) -> bool:
        """Return True when the tool ``name`` may be listed and called."""
        if _matches_any(name, self._tool_denylist):
            return False
        if self._tool_allowlist and not _matches_any(name, self._tool_allowlist):
            return False
        return True

    def resource_allowed(self, uri: str) -> bool:
        """Return True when the resource ``uri`` may be listed and read."""
        if _matches_any(uri, self._resource_denylist):
            return False
        if self._resource_allowlist and not _matches_any(uri, self._resource_allowlist):
            return False
        return True

    def filter_tools(self, names: list[str]) -> list[str]:
        """Keep only the allowed tool names, preserving order."""
        return [name for name in names if self.tool_allowed(name)]

    def filter_resources(self, uris: list[str]) -> list[str]:
        """Keep only the allowed resource URIs, preserving order."""
        return [uri for uri in uris if self.resource_allowed(uri)]
