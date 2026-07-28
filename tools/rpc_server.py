"""ZeroMQ RPC gateway for network control and feedback.

It is deliberately a control-plane sidecar. ICE/TURN and HTTP remain the
data plane; this endpoint only makes submit/status/snapshot low-latency and
machine-readable for dashboards and automation.
"""
from __future__ import annotations

import argparse, base64, hashlib, hmac, json, os, time
from datetime import datetime, timezone
from pathlib import Path
import zmq

from rpc_protocol import decode_request, encode_response


class RpcGateway:
    def __init__(self, export_dir: Path, token: str = ""):
        self.export_dir, self.token = export_dir, token

    def call(self, method: str, payload: object) -> object:
        if method == "network.snapshot":
            out = {}
            for name in ("status.current.json", "reports.recent.json"):
                path = self.export_dir / name
                if path.exists():
                    try: out[name[:-5]] = json.loads(path.read_text(encoding="utf-8"))
                    except Exception: pass
            tasks, recent_tasks = [], []
            terminal = {"completed", "failed", "dead_lettered", "cancelled", "canceled", "expired", "finalized", "resolved"}
            for path in sorted((self.export_dir / "tasks").glob("*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)[:200]:
                try:
                    item = json.loads(path.read_text(encoding="utf-8"))
                    (recent_tasks if str(item.get("status", "")).lower() in terminal else tasks).append(item)
                except Exception: pass
            out["tasks"] = tasks
            out["recent_tasks"] = recent_tasks[:50]
            return out
        if method == "task.submit":
            from mcp_server import McpTaskStore
            return McpTaskStore(self.export_dir).submit(payload)
        if method == "task.dispatch":
            # Preserve the scheduler envelope semantics used by HTTP /tasks/dispatch.
            if not isinstance(payload, dict): raise ValueError("payload_not_object")
            task_id = str(payload.get("task_id", "")).strip()
            if not task_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in task_id): raise ValueError("missing_task_id")
            for blob in payload.get("content_blobs", []):
                if not isinstance(blob, dict): continue
                cid, encoded = str(blob.get("content_id", "")).lower(), str(blob.get("data_b64", ""))
                try: data = base64.b64decode(encoded, validate=True)
                except Exception: continue
                if len(cid) == 64 and hashlib.sha256(data).hexdigest() == cid:
                    target = self.export_dir / "p2p" / cid; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            payload = dict(payload); payload["envelope_kind"] = "task"; payload["status"] = "queued"; payload["submitted_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
            tasks_dir = self.export_dir / "tasks"; tasks_dir.mkdir(parents=True, exist_ok=True)
            (tasks_dir / f"{task_id}.json").write_text(encoded, encoding="utf-8")
            with (self.export_dir / "tasks.queue.ndjson").open("a", encoding="utf-8") as queue: queue.write(encoded + "\n")
            roles = payload.get("required_roles", ["compute"])
            if isinstance(roles, list) and roles:
                with (self.export_dir / f"tasks.{str(roles[0]).lower()}.queue.ndjson").open("a", encoding="utf-8") as queue: queue.write(encoded + "\n")
            return {"status": "dispatched", "task_id": str(payload.get("task_id", ""))}
        if method == "task.status":
            task_id = str((payload or {}).get("task_id", ""))
            if not task_id: raise ValueError("missing_task_id")
            task_path = self.export_dir / "tasks" / f"{task_id}.json"
            if not task_path.exists(): raise FileNotFoundError("task_not_found")
            result = json.loads(task_path.read_text(encoding="utf-8"))
            result_path = self.export_dir / f"result.{task_id}.json"
            if result_path.exists():
                try: result["result"] = json.loads(result_path.read_text(encoding="utf-8"))
                except Exception: pass
            return result
        if method == "task.cancel":
            from mcp_server import McpTaskStore
            return McpTaskStore(self.export_dir).cancel(str((payload or {}).get("task_id", "")))
        raise ValueError("unsupported_method")


def serve(bind: str, export_dir: Path, token: str = "") -> None:
    ctx, sock = zmq.Context(), None
    try:
        sock = ctx.socket(zmq.ROUTER); sock.bind(bind)
        gateway = RpcGateway(export_dir, token)
        while True:
            frames = sock.recv_multipart()
            identity, raw = frames[0], frames[-1]
            started = time.monotonic()
            try:
                req, payload = decode_request(raw)
                if token and not hmac.compare_digest(str(req.bearer_token), token): raise PermissionError("unauthorized")
                result = gateway.call(str(req.method), payload)
                response = encode_response(str(req.request_id), True, result, duration_us=int((time.monotonic()-started)*1e6))
            except Exception as exc:
                request_id = locals().get("req").request_id if "req" in locals() else ""
                response = encode_response(str(request_id), False, {}, f"{type(exc).__name__}:{exc}", duration_us=int((time.monotonic()-started)*1e6))
            sock.send_multipart([identity, response])
    finally:
        if sock is not None: sock.close(0)
        ctx.term()


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--bind", default=os.getenv("SILICIUM_RPC_BIND", "tcp://127.0.0.1:9770")); parser.add_argument("--export-dir", default=os.getenv("SILICIUM_MCP_EXPORT_DIR", "")); parser.add_argument("--token", default=os.getenv("SILICIUM_RPC_TOKEN", ""))
    args = parser.parse_args(); serve(args.bind, Path(args.export_dir), args.token); return 0


if __name__ == "__main__": raise SystemExit(main())
