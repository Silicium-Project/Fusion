"""Isolation of the runtime, applied before any machine-learning library is
imported.

- **Offline**: the Hugging Face libraries are told never to reach the Hub;
  the node gives the runtime a directory of files it has already checked.
- **No network**: every outgoing connection other than to the loopback
  interface is refused inside the process (a second fence: the runtime
  never runs code that comes with a model, see ``loader``).
- **No code from models**: ``trust_remote_code`` is never set, weights are
  read from ``safetensors`` only, and a model directory holding Python files
  or pickle weights is refused.

The desktop app adds the OS fences (a dedicated user, no write access out of
the models directory) where the platform allows it.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path

OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "DO_NOT_TRACK": "1",
    "TOKENIZERS_PARALLELISM": "false",
    "TRANSFORMERS_NO_ADVISORY_WARNINGS": "1",
}

# Files a model directory may never hold: code, and formats whose loading
# runs code (Python pickle).
FORBIDDEN_SUFFIXES = {
    ".py", ".pyc", ".so", ".dll", ".dylib", ".exe", ".sh", ".bat",
    ".bin", ".pt", ".pth", ".pkl", ".pickle", ".joblib", ".ckpt", ".h5", ".msgpack",
}

_applied = False


def apply(home: Path) -> None:
    """Sets the offline environment and the network fence (once)."""
    global _applied
    for key, value in OFFLINE_ENV.items():
        os.environ[key] = value
    # An empty cache of our own: nothing of the user's Hugging Face cache.
    os.environ["HF_HOME"] = str(home)
    os.environ.pop("HF_TOKEN", None)
    os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
    if not _applied:
        _fence_network()
        _applied = True


def _is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if not isinstance(host, str):
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


class NetworkRefused(ConnectionRefusedError):
    """An outgoing connection the runtime does not allow."""


def _fence_network() -> None:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address):
            raise NetworkRefused(f"the Silicium AI runtime has no network access ({address!r})")
        return original_connect(self, address)

    def guarded_connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address):
            raise NetworkRefused(f"the Silicium AI runtime has no network access ({address!r})")
        return original_connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in (None, "localhost") and not _is_loopback(host if isinstance(host, str) else ""):
            raise NetworkRefused(f"the Silicium AI runtime resolves no names ({host!r})")
        return original_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.getaddrinfo = guarded_getaddrinfo


def check_model_dir(model_dir: str, models_root: Path) -> Path:
    """The model directory, when it is inside ``models_root`` and holds no
    code nor pickle file; raises ``ValueError`` otherwise."""
    root = models_root.resolve()
    path = Path(model_dir).resolve()
    if path == root or root not in path.parents:
        raise ValueError("model directory outside the models root")
    if not path.is_dir():
        raise ValueError("model directory missing")
    for file in path.rglob("*"):
        if file.is_symlink():
            raise ValueError(f"symbolic link in the model directory: {file.name}")
        if file.is_file() and file.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise ValueError(f"forbidden file in the model directory: {file.name}")
    return path
