"""``python -m silicium_ai_runtime --models-root <dir> [--port 11436]``

Started by the desktop app next to the node when AI tasks are on. The
models root is the node's ``<data dir>/ai/hf/models``: the runtime only
loads directories inside it.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import sandbox

DEFAULT_PORT = 11436


def main() -> None:
    parser = argparse.ArgumentParser(prog="silicium-ai-runtime")
    parser.add_argument("--models-root", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    args = parser.parse_args()

    models_root = args.models_root.resolve()
    models_root.mkdir(parents=True, exist_ok=True)
    # Before transformers or torch are imported.
    sandbox.apply(models_root.parent / ".hf-home")

    from .server import serve

    token = os.environ.get("SILICIUM_AI_RUNTIME_TOKEN") or None
    server = serve(args.host, args.port, models_root, token)
    print(f"Silicium AI runtime on http://{args.host}:{args.port} (models in {models_root})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
