#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qs


REPO_ROOT = Path(__file__).resolve().parents[1]
WORLD_NODE = REPO_ROOT / "tools" / "world_node.py"
WORLD_SOLANA = REPO_ROOT / "tools" / "world_solana_docker.py"
DEFAULT_PORT = 8765
DEFAULT_STATE_DIR = REPO_ROOT / ".silicium-world" / "export"
DEFAULT_TASK_JSON = '{"task_id":"demo-tile-0","kind":"compute","payload":"hello-chain","tile_index":0,"tile_region":{"x":0,"y":0,"width":1,"height":1}}'
PROFILES = {
    "france": {
        "node_id": "france-1",
        "advertise_host": "100.112.48.71",
        "seed": "http://100.112.48.71:46001",
        "roles": "verify,storage,audit",
    },
    "croatia": {
        "node_id": "croatia-1",
        "advertise_host": "100.100.81.27",
        "seed": "http://100.112.48.71:46001",
        "roles": "compute,verify,storage,audit,resource",
    },
}
DEFAULTS = dict(PROFILES["france"])


def _run(cmd: Sequence[str]) -> tuple[int, str]:
    completed = subprocess.run(
        list(cmd),
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    return int(completed.returncode), output.strip()


def _base_world_args(form: dict[str, list[str]]) -> list[str]:
    args = [
        "--node-id",
        _value(form, "node_id", DEFAULTS["node_id"]),
        "--seed",
        _value(form, "seed", DEFAULTS["seed"]),
        "--advertise-host",
        _value(form, "advertise_host", DEFAULTS["advertise_host"]),
        "--roles",
        _value(form, "roles", DEFAULTS["roles"]),
    ]
    if _value(form, "solana", "1") == "1":
        args.append("--solana")
    return args


def _value(form: dict[str, list[str]], key: str, default: str) -> str:
    values = form.get(key)
    return values[0] if values else default


def set_profile(profile: str) -> None:
    DEFAULTS.clear()
    DEFAULTS.update(PROFILES.get(profile, PROFILES["france"]))


def _extract_json(output: str) -> object | None:
    raw = (output or "").strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char not in "[{":
            continue
        try:
            parsed, end = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if raw[index + end :].strip():
            continue
        return parsed
    return None


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _iter_json_files(root: Path, pattern: str) -> list[tuple[Path, object]]:
    out: list[tuple[Path, object]] = []
    for path in sorted(root.glob(pattern)):
        data = _read_json(path)
        if data is not None:
            out.append((path, data))
    return out


def _dig(data: object, *keys: str) -> object | None:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_int(data: object, paths: Sequence[Sequence[str]]) -> int | None:
    for path in paths:
        value = _dig(data, *path)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _first_str(data: object, paths: Sequence[Sequence[str]]) -> str:
    for path in paths:
        value = _dig(data, *path)
        if value is not None and value != "":
            return str(value)
    return ""


def collect_dashboard(state_dir: Path = DEFAULT_STATE_DIR) -> dict[str, object]:
    peers = _read_json(state_dir / f"node.{DEFAULTS['node_id']}.peers.json")
    heartbeat = _read_json(state_dir / f"node.{DEFAULTS['node_id']}.heartbeat.json")
    metrics = _read_json(state_dir / f"node.{DEFAULTS['node_id']}.metrics.json")
    task_files = _iter_json_files(state_dir / "tasks", "*.json")
    request_files = _iter_json_files(state_dir / "requests", "*.json")
    result_files = _iter_json_files(state_dir, "result.*.json")
    tiles = collect_tiles(result_files)
    return {
        "node_id": DEFAULTS["node_id"],
        "state_dir": str(state_dir),
        "heartbeat": heartbeat,
        "peers": peers,
        "metrics": metrics,
        "tasks": [summarize_item(path, data, "task") for path, data in task_files],
        "requests": [summarize_item(path, data, "request") for path, data in request_files],
        "results": [summarize_result(path, data) for path, data in result_files],
        "tiles": tiles,
    }


def summarize_item(path: Path, data: object, kind: str) -> dict[str, object]:
    item_id = _first_str(data, [["task_id"], ["request_id"]]) or path.stem
    return {
        "id": item_id,
        "kind": kind,
        "status": _first_str(data, [["status"]]) or "unknown",
        "roles": _dig(data, "required_roles") or _dig(data, "target_roles") or [],
        "priority": _first_str(data, [["priority"]]),
        "updated": _first_str(data, [["updated_utc"], ["submitted_utc"]]),
    }


def summarize_result(path: Path, data: object) -> dict[str, object]:
    item_id = _first_str(data, [["task_id"], ["request_id"]]) or path.name.removeprefix("result.").removesuffix(".json")
    return {
        "id": item_id,
        "node": _first_str(data, [["node_id"], ["capacity", "node_id"]]),
        "kind": _first_str(data, [["kind"], ["role_result"], ["request_result"]]),
        "success": bool(_dig(data, "success")) if isinstance(data, dict) and "success" in data else None,
        "result_hash": _first_str(data, [["result_hash"], ["response_ref", "hash"]]),
        "finished": _first_str(data, [["finished_utc"]]),
    }


def collect_tiles(result_files: list[tuple[Path, object]]) -> list[dict[str, object]]:
    tiles: list[dict[str, object]] = []
    for path, data in result_files:
        index = _first_int(
            data,
            [
                ["tile_index"],
                ["task", "tile_index"],
                ["task", "inputs", "tile_index"],
                ["compute", "tile_index"],
                ["fragment_index"],
                ["on_chain", 0, "params", "fragment_index"],
            ],
        )
        if index is None:
            index = _first_int(data, [["task", "fragment_index"], ["fragment_id"]])
        region = _dig(data, "tile_region") or _dig(data, "task", "tile_region") or _dig(data, "task", "inputs", "tile_region")
        if index is None and not isinstance(region, dict):
            continue
        tiles.append(
            {
                "index": int(index or 0),
                "id": _first_str(data, [["tile_id"], ["task", "tile_id"], ["task_id"], ["request_id"]]) or path.name,
                "node": _first_str(data, [["node_id"], ["capacity", "node_id"]]),
                "status": "ok" if _dig(data, "success") is not False else "failed",
                "hash": _first_str(data, [["result_hash"], ["response_ref", "hash"]]),
                "region": region if isinstance(region, dict) else {},
                "image_path": _first_str(data, [["tile_image_path"], ["image_path"], ["output_path"], ["final_output", "path"]]),
            }
        )
    return sorted(tiles, key=lambda item: int(item.get("index", 0) or 0))


def parse_ppm(path: Path) -> tuple[int, int, int, bytes] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(b"P6"):
        return None
    tokens: list[bytes] = []
    index = 2
    while len(tokens) < 3 and index < len(data):
        while index < len(data) and data[index] in b" \t\r\n":
            index += 1
        if index < len(data) and data[index] == ord("#"):
            while index < len(data) and data[index] not in b"\r\n":
                index += 1
            continue
        start = index
        while index < len(data) and data[index] not in b" \t\r\n":
            index += 1
        if start < index:
            tokens.append(data[start:index])
    while index < len(data) and data[index] in b" \t\r\n":
        index += 1
    if len(tokens) != 3:
        return None
    width, height, max_value = (int(token) for token in tokens)
    pixels = data[index:]
    if width <= 0 or height <= 0 or len(pixels) < width * height * 3:
        return None
    return width, height, max_value, pixels[: width * height * 3]


def render_ppm_preview(path_value: str, *, max_cells: int = 16) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    parsed = parse_ppm(path)
    if parsed is None:
        return ""
    width, height, max_value, pixels = parsed
    step_x = max(1, width // max_cells)
    step_y = max(1, height // max_cells)
    cells: list[str] = []
    preview_w = max(1, min(max_cells, (width + step_x - 1) // step_x))
    for y in range(0, height, step_y):
        if len(cells) >= max_cells * max_cells:
            break
        for x in range(0, width, step_x):
            if len(cells) >= max_cells * max_cells:
                break
            offset = (y * width + x) * 3
            scale = 255 / max(1, max_value)
            r = int(pixels[offset] * scale)
            g = int(pixels[offset + 1] * scale)
            b = int(pixels[offset + 2] * scale)
            cells.append(f'<span style="background: rgb({r},{g},{b})"></span>')
    return (
        f'<div class="ppm-preview" style="grid-template-columns: repeat({preview_w}, 1fr);" '
        f'title="{html.escape(str(path))}">'
        + "".join(cells)
        + "</div>"
    )


def _json_html(value: object) -> str:
    if isinstance(value, dict):
        rows = []
        for key, item in value.items():
            rows.append(
                '<div class="json-row">'
                f'<span class="json-key">{html.escape(str(key))}</span>'
                f'<span class="json-value">{_json_html(item)}</span>'
                "</div>"
            )
        return '<div class="json-object">' + "".join(rows) + "</div>"
    if isinstance(value, list):
        return (
            '<div class="json-array">'
            + "".join(f'<div class="json-item">{_json_html(item)}</div>' for item in value)
            + "</div>"
        )
    if isinstance(value, bool):
        return f'<span class="json-bool">{str(value).lower()}</span>'
    if value is None:
        return '<span class="json-null">null</span>'
    if isinstance(value, (int, float)):
        return f'<span class="json-number">{value}</span>'
    return f'<span class="json-string">{html.escape(str(value))}</span>'


def render_output(output: str) -> str:
    parsed = _extract_json(output)
    if parsed is not None:
        pretty = html.escape(json.dumps(parsed, indent=2, sort_keys=True))
        return f'<div class="json-panel">{_json_html(parsed)}</div><details><summary>Raw JSON</summary><pre>{pretty}</pre></details>'
    return f"<pre>{html.escape(output or 'No output yet.')}</pre>"


def render_dashboard(data: dict[str, object]) -> str:
    heartbeat = data.get("heartbeat") if isinstance(data.get("heartbeat"), dict) else {}
    peers = data.get("peers") if isinstance(data.get("peers"), dict) else {}
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    results = data.get("results") if isinstance(data.get("results"), list) else []
    tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []
    requests = data.get("requests") if isinstance(data.get("requests"), list) else []
    tiles = data.get("tiles") if isinstance(data.get("tiles"), list) else []
    peer_rows = peers.get("peers", []) if isinstance(peers, dict) else []
    peer_count = peers.get("count", len(peer_rows)) if isinstance(peers, dict) else 0
    solana = "on" if heartbeat.get("solana_enabled") else "off"
    processed = metrics.get("processed", 0) if isinstance(metrics, dict) else 0
    failed = metrics.get("failed", 0) if isinstance(metrics, dict) else 0
    return (
        '<section class="dashboard">'
        '<div class="cards">'
        + metric_card("Node", str(data.get("node_id") or ""), f"Solana {solana}")
        + metric_card("Peers", str(peer_count), "visible nodes")
        + metric_card("Queue", str(len(tasks) + len(requests)), "local items")
        + metric_card("Results", str(len(results)), f"processed {processed} / failed {failed}")
        + "</div>"
        + render_peer_strip(peer_rows)
        + render_work_table(tasks, requests, results)
        + render_tiles(tiles)
        + "</section>"
    )


def metric_card(title: str, value: str, caption: str) -> str:
    return (
        '<div class="card">'
        f'<span class="card-title">{html.escape(title)}</span>'
        f'<strong>{html.escape(value)}</strong>'
        f'<small>{html.escape(caption)}</small>'
        "</div>"
    )


def render_peer_strip(peers: object) -> str:
    if not isinstance(peers, list) or not peers:
        return '<div class="panel"><h2>Peers & P2P Directory</h2><p class="muted">No peer snapshot yet.</p></div>'
    rows = []
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        node_id = str(peer.get("node_id") or "unknown")
        roles = ", ".join(str(role) for role in peer.get("roles", [])[:5]) if isinstance(peer.get("roles"), list) else ""
        solana = "Solana on" if _dig(peer, "capacity", "solana_enabled") else "Solana off"
        self_badge = '<span class="badge">self</span>' if peer.get("self") else ""
        
        # Outdated version detection
        version = str(peer.get("version") or _dig(peer, "capacity", "version") or "0.2.9")
        outdated_badge = '<span class="badge warning" title="Outdated node version">⚠️ Outdated v' + html.escape(version) + '</span>' if peer.get("outdated") or peer.get("outdated_version") else f'<span class="badge muted">v{html.escape(version)}</span>'

        # Transport & connection state badge (direct / relay / blocked / inactive)
        transport = str(peer.get("transport") or peer.get("status") or "direct").lower()
        if transport in ("direct", "active", "connected"):
            transport_badge = '<span class="pill green">direct</span>'
        elif transport in ("relay", "relayed"):
            transport_badge = '<span class="pill yellow">relayed</span>'
        elif transport in ("blocked", "firewalled"):
            transport_badge = '<span class="pill red">blocked</span>'
        else:
            transport_badge = f'<span class="pill gray">{html.escape(transport)}</span>'

        rows.append(
            '<div class="peer">'
            f"<strong>{html.escape(node_id)}</strong>{self_badge} {outdated_badge} {transport_badge}"
            f"<br><small>{html.escape(roles)}</small>"
            f'<span class="muted">{html.escape(solana)}</span>'
            "</div>"
        )
    return '<div class="panel"><h2>Peers & P2P Directory</h2><div class="peer-grid">' + "".join(rows) + "</div></div>"


def render_work_table(tasks: object, requests: object, results: object) -> str:
    items: list[dict[str, object]] = []
    for source in (tasks, requests, results):
        if isinstance(source, list):
            items.extend(item for item in source if isinstance(item, dict))
    if not items:
        return '<div class="panel"><h2>Tasks & results</h2><p class="muted">No task/result files found yet.</p></div>'
    rows = []
    for item in items[-12:]:
        status = item.get("status") or ("ok" if item.get("success") is not False else "failed")
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('id') or ''))}</td>"
            f"<td>{html.escape(str(item.get('kind') or ''))}</td>"
            f"<td>{html.escape(str(item.get('node') or item.get('roles') or ''))}</td>"
            f"<td><span class=\"pill\">{html.escape(str(status))}</span></td>"
            "</tr>"
        )
    return '<div class="panel"><h2>Tasks & results</h2><table><tbody>' + "".join(rows) + "</tbody></table></div>"


def render_tiles(tiles: object) -> str:
    if not isinstance(tiles, list) or not tiles:
        return '<div class="panel"><h2>Computed & Live Tiles</h2><p class="muted">No tile-indexed results yet. Tile results appear here when result files include tile_index or tile_region.</p></div>'
    count = max(len(tiles), max(int(tile.get("index", 0) or 0) for tile in tiles if isinstance(tile, dict)) + 1)
    columns = max(1, min(8, int(count**0.5) + (1 if int(count**0.5) ** 2 < count else 0)))
    tile_by_index = {int(tile.get("index", 0) or 0): tile for tile in tiles if isinstance(tile, dict)}
    cells = []
    for index in range(count):
        tile = tile_by_index.get(index)
        if tile:
            status_str = str(tile.get("status", "ok")).lower()
            verified = tile.get("verified") or tile.get("milestone_verified") or status_str in ("verified", "probabilistic_verified")
            rejected = status_str in ("failed", "rejected", "tampered")
            
            if rejected:
                tile_class = "tile rejected"
                status_badge = '<span class="badge red">❌ Rejected</span>'
            elif verified:
                tile_class = "tile verified"
                status_badge = '<span class="badge green">✓ Verified</span>'
            else:
                tile_class = "tile done"
                status_badge = '<span class="badge blue">⚡ Computed</span>'

            label = f"#{index}"
            tooltip = f"{tile.get('id', '')} {tile.get('node', '')} {tile.get('hash', '')}"
            preview = render_ppm_preview(str(tile.get("image_path") or ""))
            cells.append(
                f'<div class="{tile_class}" title="{html.escape(tooltip)}">'
                f"{preview}"
                f"<strong>{html.escape(label)}</strong> {status_badge}"
                f"<br><small>{html.escape(str(tile.get('node') or ''))}</small>"
                "</div>"
            )
        else:
            cells.append(f'<div class="tile pending"><strong>#{index}</strong><small>pending</small></div>')
    return (
        '<div class="panel"><h2>Computed & Live Tiles</h2>'
        f'<div class="tile-grid" style="grid-template-columns: repeat({columns}, minmax(54px, 1fr));">'
        + "".join(cells)
        + "</div></div>"
    )


class AppState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_title = "Ready"
        self.last_output = ""
        self.last_code = 0

    def set_result(self, title: str, code: int, output: str) -> None:
        with self.lock:
            self.last_title = title
            self.last_code = code
            self.last_output = output

    def snapshot(self) -> tuple[str, int, str]:
        with self.lock:
            return self.last_title, self.last_code, self.last_output


STATE = AppState()


class Handler(BaseHTTPRequestHandler):
    server_version = "SiliciumWorldGUI/1.0"

    def do_GET(self) -> None:
        self._send_page()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8")
        form = parse_qs(raw)
        action = _value(form, "action", "")

        try:
            code, output = self._dispatch(action, form)
            STATE.set_result(action or "Action", code, output)
        except Exception as exc:
            STATE.set_result(action or "Action", 1, f"{type(exc).__name__}: {exc}")

        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def _dispatch(self, action: str, form: dict[str, list[str]]) -> tuple[int, str]:
        py = sys.executable
        if action == "up":
            return _run([py, str(WORLD_NODE), "up", *_base_world_args(form)])
        if action == "peers":
            return _run([py, str(WORLD_NODE), "peers", *_base_world_args(form)])
        if action == "heartbeat":
            return _run([py, str(WORLD_NODE), "heartbeat", *_base_world_args(form)])
        if action == "bootstrap":
            return _run([py, str(WORLD_NODE), "bootstrap-worker", *_base_world_args(form)])
        if action == "chain_task":
            task = _value(form, "task", DEFAULT_TASK_JSON)
            parsed = json.loads(task)
            task_id = _value(form, "task_id", "")
            if not task_id and isinstance(parsed, dict):
                task_id = str(parsed.get("task_id") or parsed.get("id") or "")
            args = [py, str(WORLD_NODE), "run-chain-task", *_base_world_args(form), "--task", task]
            if task_id:
                args.extend(["--task-id", task_id])
            return _run(args)
        if action == "pubkey":
            return _run([py, str(WORLD_SOLANA), "pubkey"])
        if action == "balance":
            return _run([py, str(WORLD_SOLANA), "balance"])
        return 1, f"unknown action: {action}"

    def _send_page(self) -> None:
        title, code, output = STATE.snapshot()
        body = render_page(title, code, output)
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def render_page(title: str, code: int, output: str) -> str:
    safe_title = html.escape(title)
    rendered_output = render_output(output)
    dashboard = render_dashboard(collect_dashboard())
    status = "OK" if code == 0 else f"Exit {code}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Silicium World</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f7f8;
      color: #182025;
    }}
    body {{ margin: 0; }}
    main {{ max-width: 1160px; margin: 0 auto; padding: 28px; }}
    h1 {{ font-size: 28px; margin: 0 0 18px; }}
    form {{ display: grid; gap: 14px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    label {{ display: grid; gap: 6px; font-size: 13px; font-weight: 650; }}
    input, textarea {{ width: 100%; box-sizing: border-box; border: 1px solid #cbd5d9; border-radius: 6px; padding: 10px; font: inherit; background: white; color: #182025; }}
    textarea {{ min-height: 84px; resize: vertical; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0 18px; }}
    button {{ border: 1px solid #1b5f75; background: #1b6f87; color: white; border-radius: 6px; padding: 10px 14px; font: inherit; font-weight: 700; cursor: pointer; }}
    button.secondary {{ background: #ffffff; color: #1b5f75; }}
    section {{ margin-top: 22px; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #11181c; color: #e7f3f6; padding: 16px; border-radius: 6px; min-height: 160px; }}
    .status {{ font-weight: 800; color: #1b6f87; }}
    .json-panel {{ display: grid; gap: 8px; background: #ffffff; border: 1px solid #d7e0e3; border-radius: 6px; padding: 14px; }}
    .json-object, .json-array {{ display: grid; gap: 7px; }}
    .json-row {{ display: grid; grid-template-columns: minmax(120px, 220px) minmax(0, 1fr); gap: 12px; align-items: start; border-bottom: 1px solid #eef2f3; padding-bottom: 7px; }}
    .json-row:last-child {{ border-bottom: 0; padding-bottom: 0; }}
    .json-key {{ color: #52646c; font-size: 12px; font-weight: 800; text-transform: uppercase; overflow-wrap: anywhere; }}
    .json-value {{ overflow-wrap: anywhere; }}
    .json-string {{ color: #163d4a; }}
    .json-number {{ color: #8b3f00; font-weight: 750; }}
    .json-bool {{ color: #14643a; font-weight: 800; }}
    .json-null {{ color: #7a5d72; font-style: italic; }}
    .json-item {{ border-left: 3px solid #d7e0e3; padding-left: 10px; }}
    details {{ margin-top: 12px; }}
    summary {{ cursor: pointer; font-weight: 800; color: #1b5f75; }}
    .dashboard {{ display: grid; gap: 14px; margin: 18px 0 8px; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .card, .panel {{ background: #ffffff; border: 1px solid #d7e0e3; border-radius: 6px; padding: 14px; }}
    .card {{ display: grid; gap: 5px; }}
    .card-title, h2 {{ color: #52646c; font-size: 12px; font-weight: 850; text-transform: uppercase; margin: 0; }}
    .card strong {{ font-size: 24px; }}
    .card small, .muted {{ color: #64767d; }}
    .peer-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-top: 10px; }}
    .peer {{ display: grid; gap: 4px; border: 1px solid #e3eaed; border-radius: 6px; padding: 10px; }}
    .badge, .pill {{ display: inline-flex; width: fit-content; border-radius: 999px; background: #dff2ea; color: #14643a; padding: 2px 8px; font-size: 12px; font-weight: 800; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    td {{ border-top: 1px solid #eef2f3; padding: 9px 8px; overflow-wrap: anywhere; }}
    .tile-grid {{ display: grid; gap: 8px; margin-top: 12px; }}
    .tile {{ aspect-ratio: 1; min-height: 58px; border-radius: 6px; border: 1px solid #d7e0e3; display: grid; place-items: center; text-align: center; padding: 6px; }}
    .tile.done {{ background: #dff2ea; border-color: #95d4b8; color: #123d2a; }}
    .tile.pending {{ background: #f0f3f4; color: #6d7b80; }}
    .tile small {{ font-size: 11px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }}
    .ppm-preview {{ width: 100%; max-width: 92px; display: grid; gap: 0; border: 1px solid rgba(0,0,0,.12); image-rendering: pixelated; }}
    .ppm-preview span {{ aspect-ratio: 1; min-width: 2px; }}
    @media (max-width: 760px) {{ .grid {{ grid-template-columns: 1fr; }} main {{ padding: 18px; }} }}
    @media (max-width: 900px) {{ .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
  </style>
</head>
<body>
  <main>
    <h1>Silicium World</h1>
    <form method="post">
      <div class="grid">
        <label>Node ID <input name="node_id" value="{html.escape(DEFAULTS["node_id"])}"></label>
        <label>Advertise host <input name="advertise_host" value="{html.escape(DEFAULTS["advertise_host"])}"></label>
        <label>Seed <input name="seed" value="{html.escape(DEFAULTS["seed"])}"></label>
        <label>Roles <input name="roles" value="{html.escape(DEFAULTS["roles"])}"></label>
      </div>
      <input type="hidden" name="solana" value="1">
      <label>Task ID <input name="task_id" value="demo-tile-0"></label>
      <label>Chain task JSON <textarea name="task">{html.escape(DEFAULT_TASK_JSON)}</textarea></label>
      <div class="actions">
        <button name="action" value="up">Start Node</button>
        <button class="secondary" name="action" value="pubkey">Wallet Pubkey</button>
        <button class="secondary" name="action" value="balance">Wallet Balance</button>
        <button name="action" value="bootstrap">Bootstrap Worker</button>
        <button class="secondary" name="action" value="peers">Peers</button>
        <button class="secondary" name="action" value="heartbeat">Heartbeat</button>
        <button name="action" value="chain_task">Run Chain Task</button>
      </div>
    </form>
    {dashboard}
    <section>
      <div><strong>{safe_title}</strong> <span class="status">{html.escape(status)}</span></div>
      {rendered_output}
    </section>
  </main>
</body>
</html>"""


def main(argv: Sequence[str] | None = None) -> int:
    parser = __import__("argparse").ArgumentParser(description="Local Silicium world GUI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--profile", choices=sorted(PROFILES), default=os.environ.get("SILICIUM_WORLD_GUI_PROFILE", "france"))
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)
    set_profile(args.profile)

    url = f"http://{args.host}:{args.port}"
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Silicium World GUI: {url}")
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
