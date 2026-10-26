"""Loading a model of the catalogue from its checked directory.

The manifest (``silicium-model/1``, written by the BackEnd's catalogue and
checked by the node) says the task and the library. Nothing here names a
model: ``transformers`` reads ``config.json`` and its own registry of
architectures, ``sentence-transformers`` and ``timm`` their configuration
files. A model whose architecture the installed library does not know is
refused (no code is ever taken from a model).

Loaded models are kept in a small LRU cache (``SILICIUM_AI_MAX_LOADED``,
default 2): a worker usually runs one model for many fragments.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ModelError(ValueError):
    """A model the runtime cannot load (sent back to the node)."""


@dataclass
class Loaded:
    task: str
    library: str
    model: Any
    kind: str  # "pipeline", "sentence-transformer", "cross-encoder", "timm"
    extra: Any = None


def device() -> str:
    import torch

    wanted = os.environ.get("SILICIUM_AI_DEVICE", "auto").strip().lower()
    if wanted == "cpu":
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() and wanted != "cuda":
        return "mps"
    return "cpu"


def _check_architecture(manifest: dict) -> None:
    """Refuses a transformers model whose type the library does not know."""
    from transformers.models.auto.configuration_auto import CONFIG_MAPPING

    model_type = (manifest.get("loader") or {}).get("model_type", "")
    if model_type and model_type not in CONFIG_MAPPING:
        raise ModelError(f"architecture {model_type!r} unknown to transformers (custom code is never run)")


def _pipeline(task: str, path: Path, manifest: dict) -> Loaded:
    import transformers

    _check_architecture(manifest)
    variant = (manifest.get("loader") or {}).get("variant") or None
    model_kwargs: dict[str, Any] = {"use_safetensors": True}
    if variant:
        model_kwargs["variant"] = variant
    try:
        pipe = transformers.pipeline(
            task=task,
            model=str(path),
            trust_remote_code=False,
            model_kwargs=model_kwargs,
            device=device(),
        )
    except Exception as err:
        raise ModelError(f"{type(err).__name__}: {err}") from err
    return Loaded(task=task, library="transformers", model=pipe, kind="pipeline")


def _sentence_transformers(task: str, path: Path) -> Loaded:
    from sentence_transformers import CrossEncoder, SentenceTransformer

    try:
        if task == "text-ranking":
            model = CrossEncoder(str(path), device=device(), trust_remote_code=False, local_files_only=True)
            return Loaded(task, "sentence-transformers", model, "cross-encoder")
        model = SentenceTransformer(str(path), device=device(), trust_remote_code=False, local_files_only=True)
    except Exception as err:
        raise ModelError(f"{type(err).__name__}: {err}") from err
    return Loaded(task, "sentence-transformers", model, "sentence-transformer")


def _timm(task: str, path: Path) -> Loaded:
    import timm

    try:
        kwargs = {"num_classes": 0} if task == "image-feature-extraction" else {}
        model = timm.create_model(f"local-dir:{path}", pretrained=True, **kwargs)
        model.eval().to(device())
        config = timm.data.resolve_data_config({}, model=model)
        transform = timm.data.create_transform(**config)
    except Exception as err:
        raise ModelError(f"{type(err).__name__}: {err}") from err
    labels = getattr(model, "pretrained_cfg", {}).get("label_names")
    return Loaded(task, "timm", model, "timm", extra={"transform": transform, "labels": labels})


def load(task: str, path: Path, manifest: dict) -> Loaded:
    library = manifest.get("library", "")
    if manifest.get("task") != task:
        raise ModelError("the manifest is for another task")
    if library == "transformers":
        return _pipeline(task, path, manifest)
    if library == "sentence-transformers":
        if task in ("feature-extraction", "sentence-similarity", "text-ranking"):
            return _sentence_transformers(task, path)
        return _pipeline(task, path, manifest)
    if library == "timm":
        if task in ("image-classification", "image-feature-extraction"):
            return _timm(task, path)
        raise ModelError(f"timm does not run {task}")
    raise ModelError(f"library {library!r} not run by this runtime")


class Cache:
    """Loaded models by (directory, digest, task), least recently used out."""

    def __init__(self, size: int | None = None):
        self.size = size or max(1, int(os.environ.get("SILICIUM_AI_MAX_LOADED", "2") or 2))
        self.items: OrderedDict[tuple, Loaded] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, task: str, path: Path, manifest: dict) -> Loaded:
        key = (str(path), manifest.get("digest", ""), task)
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
        loaded = load(task, path, manifest)
        with self.lock:
            self.items[key] = loaded
            while len(self.items) > self.size:
                self.items.popitem(last=False)
        return loaded
