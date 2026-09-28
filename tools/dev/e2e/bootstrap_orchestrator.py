#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, object]) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class OrchestratorHandler(BaseHTTPRequestHandler):
    server_version = "SiliciumOrchestrator/1.0"

    def _state(self) -> dict[str, object]:
        return getattr(self.server, "state", {})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/healthz"}:
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "service": "orchestrator",
                    "status": "ok",
                    "node_id": self._state().get("node_id", ""),
                    "port": self._state().get("port", 0),
                    "generated_utc": _utc_now(),
                },
            )
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"status": "not_found", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/gossip/publish":
            _json_response(self, HTTPStatus.NOT_FOUND, {"status": "not_found", "path": self.path})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(max(0, length)) if length else b""
        payload: dict[str, object] | None = None
        if raw:
            try:
                decoded = json.loads(raw.decode("utf-8"))
                if isinstance(decoded, dict):
                    payload = decoded
            except Exception:
                payload = None

        export_dir = self._state().get("export_dir")
        if isinstance(export_dir, Path):
            export_dir.mkdir(parents=True, exist_ok=True)
            try:
                (export_dir / "gossip.last.json").write_text(
                    json.dumps(
                        {
                            "received_utc": _utc_now(),
                            "path": self.path,
                            "headers": {k: v for k, v in self.headers.items()},
                            "payload": payload,
                        },
                        indent=2,
                        ensure_ascii=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except Exception:
                pass

        _json_response(
            self,
            HTTPStatus.OK,
            {
                "status": "ok",
                "received_bytes": len(raw),
                "received_utc": _utc_now(),
            },
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal Silicium orchestrator gossip server")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=46100)
    parser.add_argument("--node-id", default="orchestrator-1")
    parser.add_argument("--export-dir", type=Path, default=Path("/var/lib/silicium/network/orchestrator/export"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.export_dir.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((args.bind, args.port), OrchestratorHandler)
    server.state = {
        "node_id": args.node_id,
        "port": args.port,
        "export_dir": args.export_dir,
    }
    print(f"silicium orchestrator listening on {args.bind}:{args.port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
