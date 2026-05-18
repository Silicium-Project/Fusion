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
            task = _value(form, "task", '{"kind":"compute","payload":"hello-chain"}')
            json.loads(task)
            return _run([py, str(WORLD_NODE), "run-chain-task", *_base_world_args(form), "--task", task])
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
    main {{ max-width: 980px; margin: 0 auto; padding: 28px; }}
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
    @media (max-width: 760px) {{ .grid {{ grid-template-columns: 1fr; }} main {{ padding: 18px; }} }}
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
      <label>Chain task JSON <textarea name="task">{{"kind":"compute","payload":"hello-chain"}}</textarea></label>
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
