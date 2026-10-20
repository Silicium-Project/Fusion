"""The local HTTP API the node calls (``SILICIUM_AI_RUNTIME_URL``).

- ``GET /v1/health``: format, version, device, the tasks this runtime runs.
- ``POST /v1/load`` ``{model_dir, manifest}``: loads a model (refused with
  422 and a message when the runtime cannot run it).
- ``POST /v1/run`` ``{task, model_dir, manifest, parameters, seed, items}``:
  one output per item (``{"id", "inputs"}``), in order.

It listens on the loopback interface only; with ``SILICIUM_AI_RUNTIME_TOKEN``
set, every call needs it as a bearer token. One computation at a time: the
models are not thread-safe and the machine's cores are already busy.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, sandbox
from .inputs import InputError
from .loader import Cache, ModelError

FORMAT = "silicium-ai-runtime/1"
MAX_BODY_BYTES = 256 << 20
MAX_ITEMS = 1_000


class Runtime:
    """State shared by the requests."""

    def __init__(self, models_root: Path, token: str | None):
        self.models_root = models_root
        self.token = token
        self.cache = Cache()
        self.compute = threading.Lock()

    def health(self) -> dict:
        from . import tasks
        from .loader import device

        libraries = {}
        for name in ("torch", "transformers", "sentence_transformers", "timm"):
            try:
                libraries[name] = __import__(name).__version__
            except Exception:  # A missing library only removes its tasks.
                pass
        return {
            "format": FORMAT,
            "version": __version__,
            "device": device(),
            "libraries": libraries,
            "tasks": sorted(tasks.TASKS) if "transformers" in libraries else [],
        }

    def _model(self, body: dict):
        from . import tasks

        task = body.get("task") or (body.get("manifest") or {}).get("task")
        if task not in tasks.TASKS:
            raise InputError(f"task {task!r} not run by this runtime")
        manifest = body.get("manifest")
        if not isinstance(manifest, dict) or manifest.get("format") != "silicium-model/1":
            raise InputError("missing model manifest")
        try:
            path = sandbox.check_model_dir(str(body.get("model_dir", "")), self.models_root)
        except ValueError as err:
            raise ModelError(str(err)) from err
        return self.cache.get(task, path, manifest)

    def load(self, body: dict) -> dict:
        with self.compute:
            self._model(body)
        return {"loaded": True}

    def run(self, body: dict) -> dict:
        from . import tasks

        items = body.get("items")
        if not isinstance(items, list) or not items or len(items) > MAX_ITEMS:
            raise InputError(f"expected 1 to {MAX_ITEMS} items")
        parameters = body.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise InputError("parameters must be an object")
        seed = body.get("seed", 0)
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise InputError("seed must be an integer")
        with self.compute:
            model = self._model(body)
            import torch

            outputs = []
            for item in items:
                if not isinstance(item, dict) or "inputs" not in item:
                    raise InputError('every item needs "inputs"')
                torch.manual_seed(seed % (2**63))
                try:
                    outputs.append(tasks.run(model, item["inputs"], parameters))
                except InputError as err:
                    raise InputError(f"item {item.get('id')}: {err}") from err
        return {"outputs": outputs}


def handler_for(runtime: Runtime):
    class Handler(BaseHTTPRequestHandler):
        server_version = "silicium-ai-runtime"
        sys_version = ""

        def log_message(self, format, *args):  # noqa: A002 - signature of the base class.
            if os.environ.get("SILICIUM_AI_RUNTIME_LOG") == "1":
                super().log_message(format, *args)

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if not runtime.token:
                return True
            given = self.headers.get("Authorization", "")
            return hmac.compare_digest(given.encode(), f"Bearer {runtime.token}".encode())

        def do_GET(self):  # noqa: N802 - name of the base class.
            if not self._authorized():
                return self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            if self.path == "/v1/health":
                return self._send(HTTPStatus.OK, runtime.health())
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self):  # noqa: N802 - name of the base class.
            if not self._authorized():
                return self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            actions = {"/v1/load": runtime.load, "/v1/run": runtime.run}
            action = actions.get(self.path)
            if action is None:
                return self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY_BYTES:
                return self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body_size"})
            try:
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise InputError("expected a JSON object")
                self._send(HTTPStatus.OK, action(body))
            except (InputError, json.JSONDecodeError) as err:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "input", "message": str(err)})
            except ModelError as err:
                self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "model", "message": str(err)})
            except Exception as err:  # A failed computation: the node gives up this fragment.
                traceback.print_exc()
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "compute", "message": f"{type(err).__name__}: {err}"})

    return Handler


def serve(host: str, port: int, models_root: Path, token: str | None) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("the Silicium AI runtime only listens on the loopback interface")
    server = ThreadingHTTPServer((host, port), handler_for(Runtime(models_root, token)))
    server.daemon_threads = True
    return server
