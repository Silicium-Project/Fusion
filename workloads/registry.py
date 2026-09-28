"""Workload registry: the single place that knows which workloads exist and how
a node executes them.

Every workload is a folder under ``workloads/<category>/...`` holding a
``manifest.yaml`` (schema: ``workloads/schema/workload-manifest-v2.schema.json``).
The ``runtime`` section of the manifest says how to run it:

- ``kind: python`` + ``handler: package.module:function``: the node calls
  ``function(WorkloadContext)`` and returns its result dict;
- ``kind: planned``: descriptive profile only, no node executes it yet.

Adding a workload therefore means adding a folder with a manifest (and a
handler for executable ones); no node code has to change.

Nodes do not parse YAML (PyYAML is not installed everywhere a node runs):
they read ``workloads/index.json``, generated from the manifests by
``./silicium workload index``. ``./silicium workload lint`` fails when the
index is out of date.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

WORKLOADS_ROOT = Path(__file__).resolve().parent
MANIFEST_NAME = "manifest.yaml"
INDEX_NAME = "index.json"
INDEX_SCHEMA = "silicium.workload-index.v1"
# Manifest fields a node needs at run time; everything else stays in the YAML.
INDEX_FIELDS = ("id", "version", "aliases", "runtime", "parameters")
CATEGORY_ROLES = {"calcul": "compute", "verification": "verify"}


class WorkloadError(RuntimeError):
    """Raised when the catalogue is inconsistent or a handler cannot be loaded."""


@dataclass(frozen=True)
class WorkloadContext:
    """What a handler receives. Only the fields a handler needs are used."""

    workload: str
    task: Mapping[str, Any]
    p2p_data: bytes
    p2p_meta: Mapping[str, Any]
    put_output: Callable[[bytes], dict[str, Any]]
    envelope: Mapping[str, Any] = field(default_factory=dict)
    fetch: Callable[[Mapping[str, Any]], tuple[bytes, dict[str, Any]]] | None = None
    run_process: Callable[..., Any] | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)


Handler = Callable[[WorkloadContext], dict[str, Any]]


@dataclass(frozen=True)
class WorkloadSpec:
    id: str
    version: str
    role: str
    runtime_kind: str
    handler_ref: str | None
    aliases: tuple[str, ...]
    parameters: Mapping[str, Any]
    manifest_path: Path

    @property
    def executable(self) -> bool:
        return self.runtime_kind == "python" and bool(self.handler_ref)

    def load_handler(self) -> Handler:
        if not self.executable or not self.handler_ref:
            raise WorkloadError(f"workload_not_executable:{self.id}")
        return _import_handler(self.handler_ref)


@lru_cache(maxsize=None)
def _import_handler(reference: str) -> Handler:
    module_name, _, attribute = reference.partition(":")
    try:
        module = importlib.import_module(module_name)
        handler = getattr(module, attribute)
    except (ImportError, AttributeError) as exc:
        raise WorkloadError(f"workload_handler_unavailable:{reference}:{exc}") from exc
    if not callable(handler):
        raise WorkloadError(f"workload_handler_not_callable:{reference}")
    return handler


def normalize_workload_id(workload: object) -> str:
    return str(workload or "").strip().lower()


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML is in requirements-p2p.txt
        raise WorkloadError("workload_registry_requires_pyyaml") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise WorkloadError(f"workload_manifest_not_a_mapping:{path}")
    return data


def spec_from_manifest(path: Path, data: Mapping[str, Any]) -> WorkloadSpec:
    workload_id = normalize_workload_id(data.get("id"))
    category = workload_id.split("/", 1)[0]
    role = CATEGORY_ROLES.get(category)
    if not workload_id or role is None:
        raise WorkloadError(f"workload_manifest_id_invalid:{path}")
    runtime = data.get("runtime") if isinstance(data.get("runtime"), Mapping) else {}
    parameters = data.get("parameters") if isinstance(data.get("parameters"), Mapping) else {}
    return WorkloadSpec(
        id=workload_id,
        version=str(data.get("version", "")),
        role=role,
        runtime_kind=str(runtime.get("kind", "planned")),
        handler_ref=str(runtime["handler"]) if runtime.get("handler") else None,
        aliases=tuple(normalize_workload_id(alias) for alias in data.get("aliases") or ()),
        parameters=dict(parameters),
        manifest_path=path,
    )


class WorkloadRegistry:
    def __init__(self, specs: Iterable[WorkloadSpec]) -> None:
        self._specs: dict[str, WorkloadSpec] = {}
        self._names: dict[str, str] = {}
        for spec in specs:
            if spec.id in self._specs:
                raise WorkloadError(f"workload_id_duplicate:{spec.id}")
            self._specs[spec.id] = spec
            for name in (spec.id, *spec.aliases):
                if name in self._names:
                    raise WorkloadError(f"workload_name_duplicate:{name}")
                self._names[name] = spec.id

    @classmethod
    def load(cls, root: Path = WORKLOADS_ROOT) -> "WorkloadRegistry":
        """Registry from the generated index (what nodes use)."""
        index_path = root / INDEX_NAME
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkloadError(f"workload_index_unreadable:{index_path}:{exc}") from exc
        if not isinstance(index, Mapping) or index.get("schema") != INDEX_SCHEMA:
            raise WorkloadError(f"workload_index_schema_invalid:{index_path}")
        return cls(
            spec_from_manifest(root / entry["path"] / MANIFEST_NAME, entry)
            for entry in index.get("workloads", [])
        )

    @classmethod
    def from_manifests(cls, root: Path = WORKLOADS_ROOT) -> "WorkloadRegistry":
        """Registry read directly from the YAML manifests (needs PyYAML)."""
        manifests = sorted(root.rglob(MANIFEST_NAME))
        return cls(spec_from_manifest(path, _load_yaml(path)) for path in manifests)

    def get(self, workload: object) -> WorkloadSpec | None:
        canonical = self._names.get(normalize_workload_id(workload))
        return self._specs.get(canonical) if canonical else None

    def specs(self) -> list[WorkloadSpec]:
        return [self._specs[key] for key in sorted(self._specs)]

    def handler_for(self, workload: object, role: str) -> tuple[WorkloadSpec, Handler] | None:
        """Handler for an executable workload of this role, else ``None``."""
        spec = self.get(workload)
        if spec is None or spec.role != role or not spec.executable:
            return None
        return spec, spec.load_handler()


def build_index(root: Path = WORKLOADS_ROOT) -> dict[str, Any]:
    """Index content for ``root`` (needs PyYAML); see ``write_index``."""
    entries = []
    for path in sorted(root.rglob(MANIFEST_NAME)):
        data = _load_yaml(path)
        entry = {key: data[key] for key in INDEX_FIELDS if key in data}
        entry["path"] = path.parent.relative_to(root).as_posix()
        entries.append(entry)
    entries.sort(key=lambda entry: str(entry.get("id", "")))
    return {"schema": INDEX_SCHEMA, "workloads": entries}


def render_index(index: Mapping[str, Any]) -> str:
    return json.dumps(index, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def index_is_current(root: Path = WORKLOADS_ROOT) -> bool:
    path = root / INDEX_NAME
    return path.is_file() and path.read_text(encoding="utf-8") == render_index(build_index(root))


def write_index(root: Path = WORKLOADS_ROOT) -> Path:
    path = root / INDEX_NAME
    path.write_text(render_index(build_index(root)), encoding="utf-8")
    return path


@lru_cache(maxsize=1)
def default_registry() -> WorkloadRegistry:
    return WorkloadRegistry.load()


def run_workload(
    workload: object,
    role: str,
    context_fields: Mapping[str, Any],
    registry: WorkloadRegistry | None = None,
) -> dict[str, Any] | None:
    """Run ``workload`` if the registry has an executable handler for ``role``.

    Returns ``None`` when there is none, so the caller can apply its generic
    behaviour for unknown or descriptive-only workloads.
    """
    found = (registry or default_registry()).handler_for(workload, role)
    if found is None:
        return None
    spec, handler = found
    # Handlers see the ID the task asked for (an alias stays an alias in the
    # result); `parameters` come from the manifest.
    context = WorkloadContext(
        workload=normalize_workload_id(workload),
        parameters=spec.parameters,
        **context_fields,
    )
    return handler(context)


def unsupported_reason(workload: object, registry: WorkloadRegistry | None = None) -> str:
    """Why a compute task was not executed (reported in the task result)."""
    if not normalize_workload_id(workload):
        return "unsupported_workload"
    spec = (registry or default_registry()).get(workload)
    if spec is None:
        return "unsupported_workload"
    if not spec.executable:
        return "workload_not_executable"
    return "workload_role_mismatch"
