"""ZeroMQ RPC gateway for network control and feedback.

It is deliberately a control-plane sidecar. ICE/TURN and HTTP remain the
data plane; this endpoint only makes submit/status/snapshot low-latency and
machine-readable for dashboards and automation.
"""
from __future__ import annotations

import argparse, base64, hashlib, hmac, json, os, threading, time
from datetime import datetime, timezone
from pathlib import Path
import zmq

from rpc_protocol import decode_request, encode_response


def _priority_rank(priority: str) -> int:
    return {"low": 10, "normal": 50, "high": 80, "urgent": 100}.get(priority, 50)


def append_rpc_event(export_dir: Path, event: str, task_id: str, **details: object) -> None:
    export_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "event": event,
        "item_id": task_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **details,
    }
    with (export_dir / "rpc.events.ndjson").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n")


class RpcGateway:
    def __init__(self, export_dir: Path, token: str = "", events_bind: str = ""):
        self.export_dir, self.token, self.events_bind = export_dir, token, events_bind

    def read_events(self, payload: object) -> dict[str, object]:
        """Read the durable control-plane journal from a byte cursor.

        PUB/SUB is intentionally best-effort; callers recover missed messages
        from this cursor-based API or from ``network.snapshot``.  Result bytes
        are never present in the journal.
        """
        request = payload if isinstance(payload, dict) else {}
        try:
            cursor = max(0, int(request.get("cursor", 0) or 0))
        except (TypeError, ValueError):
            raise ValueError("invalid_event_cursor") from None
        try:
            limit = min(500, max(1, int(request.get("limit", 100) or 100)))
        except (TypeError, ValueError):
            raise ValueError("invalid_event_limit") from None
        path = self.export_dir / "rpc.events.ndjson"
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return {"events": [], "cursor": 0}
        # A compacted/recreated journal invalidates an old cursor cleanly.
        if cursor > size:
            cursor = 0
        events: list[object] = []
        with path.open("rb") as stream:
            stream.seek(cursor)
            while len(events) < limit:
                line = stream.readline()
                if not line:
                    break
                cursor = stream.tell()
                try:
                    event = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(event, dict):
                    events.append(event)
        return {"events": events, "cursor": cursor}

    def terminalize_task(self, payload: object, status: str) -> dict[str, object]:
        """Resolve an orphaned scheduler envelope without fabricating a result.

        This is deliberately limited to the authenticated control plane.  A
        normal queued task still uses ``task.cancel``; this operation is for a
        task already dispatched to a worker that has demonstrably disappeared
        or can no longer run it.  The durable state and event journal change
        together so dashboards cannot retain a phantom running task.
        """
        request = payload if isinstance(payload, dict) else {}
        task_id = str(request.get("task_id", "")).strip()
        reason = str(request.get("reason", "")).strip() or "operator_resolved_orphan"
        if not task_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in task_id):
            raise ValueError("missing_task_id")
        path = self.export_dir / "tasks" / f"{task_id}.json"
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        if not isinstance(task, dict):
            raise ValueError("task_invalid")
        current = str(task.get("status", "")).lower()
        terminal = {"completed", "failed", "dead_lettered", "cancelled", "canceled", "expired", "finalized", "resolved"}
        if current in terminal:
            return task
        task["status"] = status
        task["terminal_reason"] = reason
        task["terminal_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        task["handled_by"] = "rpc-control"
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(task, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
        temporary.replace(path)
        append_rpc_event(self.export_dir, "task.terminal", task_id, status=status, handled_by="rpc-control", reason=reason)
        return task

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
            out["rpc_events"] = {
                "transport": "zeromq-pubsub",
                "endpoint": self.events_bind,
                "topic_prefix": "task.",
                "replay_method": "task.events",
            }
            return out
        if method == "task.events":
            return self.read_events(payload)
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
            priority = str(payload.get("priority", "normal")).strip().lower() or "normal"
            payload = dict(payload)
            payload["envelope_kind"] = "task"
            payload["status"] = "queued"
            payload["submitted_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            payload["priority"] = priority
            payload["priority_rank"] = _priority_rank(priority)
            encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
            tasks_dir = self.export_dir / "tasks"; tasks_dir.mkdir(parents=True, exist_ok=True)
            (tasks_dir / f"{task_id}.json").write_text(encoded, encoding="utf-8")
            with (self.export_dir / "tasks.queue.ndjson").open("a", encoding="utf-8") as queue: queue.write(encoded + "\n")
            roles = payload.get("required_roles", ["compute"])
            if isinstance(roles, list) and roles:
                with (self.export_dir / f"tasks.{str(roles[0]).lower()}.queue.ndjson").open("a", encoding="utf-8") as queue: queue.write(encoded + "\n")
            append_rpc_event(self.export_dir, "task.queued", task_id, required_roles=roles)
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
        if method == "task.expire":
            return self.terminalize_task(payload, "expired")
        raise ValueError("unsupported_method")


def publish_events(export_dir: Path, bind: str, stop: threading.Event) -> None:
    """Bridge the durable event log to PUB/SUB without carrying artifacts."""
    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.bind(bind)
    path = export_dir / "rpc.events.ndjson"
    # Live PUB/SUB deliberately starts at EOF.  A fresh subscriber gets its
    # authoritative catch-up through task.events, not a potentially huge and
    # duplicated replay every time the service restarts.
    try:
        offset = path.stat().st_size
    except FileNotFoundError:
        offset = 0
    try:
        while not stop.wait(0.025):
            try:
                with path.open("rb") as stream:
                    if offset > path.stat().st_size:
                        offset = 0
                    stream.seek(offset)
                    chunk = stream.read()
                    offset = stream.tell()
            except FileNotFoundError:
                continue
            for line in chunk.splitlines():
                try:
                    event = json.loads(line.decode("utf-8"))
                    item_id = str(event.get("item_id", ""))
                    publisher.send_multipart([f"task.{item_id}".encode("utf-8"), json.dumps(event, separators=(",", ":")).encode("utf-8")])
                except Exception:
                    continue
    finally:
        publisher.close(0)
        context.term()


def serve(bind: str, export_dir: Path, token: str = "", events_bind: str = "") -> None:
    ctx, sock = zmq.Context(), None
    event_stop = threading.Event()
    event_thread: threading.Thread | None = None
    try:
        sock = ctx.socket(zmq.ROUTER); sock.bind(bind)
        if events_bind:
            event_thread = threading.Thread(target=publish_events, args=(export_dir, events_bind, event_stop), name="silicium-rpc-events", daemon=True)
            event_thread.start()
        gateway = RpcGateway(export_dir, token, events_bind)
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
        event_stop.set()
        if event_thread is not None:
            event_thread.join(timeout=1.0)
        if sock is not None: sock.close(0)
        ctx.term()


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--bind", default=os.getenv("SILICIUM_RPC_BIND", "tcp://127.0.0.1:9770")); parser.add_argument("--events-bind", default=os.getenv("SILICIUM_RPC_EVENTS_BIND", "tcp://127.0.0.1:9771")); parser.add_argument("--export-dir", default=os.getenv("SILICIUM_MCP_EXPORT_DIR", "")); parser.add_argument("--token", default=os.getenv("SILICIUM_RPC_TOKEN", ""))
    args = parser.parse_args(); serve(args.bind, Path(args.export_dir), args.token, args.events_bind); return 0


if __name__ == "__main__": raise SystemExit(main())
