"""Input normalisation for task and request envelopes.

Every function raises ``ValueError`` with a stable machine-readable code; the
HTTP layer forwards that code to clients as ``detail``, so the codes are part
of the API.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .constants import NETWORK_ROLES, P2P_PROTOCOLS, PRIORITIES

_SAFE_TASK_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")

_PRIORITY_RANKS = {"low": 10, "normal": 50, "high": 80, "urgent": 100}

# Task "kind"/"type" aliases (including French spellings) mapped to the role
# that should execute the task.
_TASK_KIND_ROLES = {
    "compute": "compute",
    "calculation": "compute",
    "calcul": "compute",
    "verification": "verify",
    "verify": "verify",
    "storage": "storage",
    "store": "storage",
    "audit": "audit",
    "resource": "resource",
}


def sanitize_task_id(task_id: str) -> str:
    """Make an id safe to use as a file name (also used for request/node ids)."""
    task_id = task_id.strip()
    if not task_id:
        return ""
    return _SAFE_TASK_ID_RE.sub("_", task_id)


def csv_values(raw: str) -> list[str]:
    """Split a comma-separated string, dropping blanks."""
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def priority_rank(priority: str) -> int:
    """Return the numeric scheduling rank of a priority (unknown -> normal)."""
    return _PRIORITY_RANKS.get(priority, 50)


def normalized_priority(value: Any) -> str:
    """Validate a priority, defaulting to ``normal``."""
    priority = str(value or "normal").strip().lower()
    if priority not in PRIORITIES:
        raise ValueError("unsupported_priority")
    return priority


def normalized_roles(value: Any, default: list[str] | None = None) -> list[str]:
    """Validate a role list given as CSV string or array; returns sorted unique roles."""
    if value is None:
        return list(default or ["compute"])
    if isinstance(value, str):
        roles = csv_values(value)
    elif isinstance(value, list):
        roles = [str(item).strip().lower() for item in value if str(item).strip()]
    else:
        raise ValueError("roles_not_array")
    roles = sorted(set(roles))
    if not roles:
        raise ValueError("roles_empty")
    unsupported = [role for role in roles if role not in NETWORK_ROLES]
    if unsupported:
        raise ValueError("unsupported_role:" + ",".join(unsupported))
    return roles


def validate_p2p_ref(value: Any, *, required: bool = False) -> dict[str, Any] | None:
    """Normalise a content reference to ``{protocol, content_id, ...}``."""
    if value is None:
        if required:
            raise ValueError("missing_p2p_ref")
        return None
    if not isinstance(value, dict):
        raise ValueError("p2p_ref_not_object")
    protocol = str(value.get("protocol", "ipfs")).strip().lower()
    if protocol not in P2P_PROTOCOLS:
        raise ValueError("unsupported_p2p_protocol")
    content_id = str(value.get("cid") or value.get("content_id") or value.get("url") or "").strip()
    if not content_id:
        raise ValueError("missing_p2p_content_id")
    normalized: dict[str, Any] = {"protocol": protocol, "content_id": content_id}
    for key in ("hash", "size_bytes", "mime_type"):
        if key in value:
            normalized[key] = value[key]
    return normalized


def validate_on_chain(value: Any) -> dict[str, Any] | None:
    """Accept an optional on-chain metadata object (copied, not inspected)."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("on_chain_not_object")
    return dict(value)


def default_task_roles(task: Mapping[str, Any]) -> list[str]:
    """Infer the required role from the task's ``kind``/``type`` field."""
    kind = str(task.get("kind", task.get("type", "compute"))).strip().lower()
    return [_TASK_KIND_ROLES.get(kind, "compute")]
