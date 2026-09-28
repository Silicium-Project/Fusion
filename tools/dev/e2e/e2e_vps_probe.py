#!/usr/bin/env python3
"""E2E probe that checks a deployed orchestrator is reachable and answers its control endpoints (dev only)."""
from __future__ import annotations

import argparse
import json
import os
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _normalized_base_url(control_url: str) -> str:
    value = str(control_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("missing_control_url")
    if value.endswith("/gossip/publish"):
        return value[: -len("/gossip/publish")]
    return value


def _control_host(control_url: str) -> str:
    parsed = urlparse(_normalized_base_url(control_url))
    host = str(parsed.hostname or "").strip()
    if host:
        return host
    raise ValueError("missing_control_host")


def _http_json(url: str, *, method: str = "GET", payload: dict[str, object] | None = None, timeout_s: float = 5.0) -> dict[str, object]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def _resolve_host(host: str) -> list[str]:
    addresses: list[str] = []
    for family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(host, None):
        if family == socket.AF_INET:
            addresses.append(str(sockaddr[0]))
        elif family == socket.AF_INET6:
            addresses.append(str(sockaddr[0]))
    return sorted(dict.fromkeys(addresses))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe the VPS/orchestrator DNS and gossip endpoint.")
    parser.add_argument("--control-url", default="", help="Orchestrator gossip publish URL.")
    parser.add_argument("--probe-id", default="backend-probe")
    parser.add_argument("--output", default="", help="Optional JSON report path.")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--retries", type=int, default=24)
    parser.add_argument("--delay-s", type=float, default=1.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    control_url = args.control_url or os.environ.get("SILICIUM_CONTROL_URL", "")
    base_url = _normalized_base_url(control_url)
    control_host = _control_host(control_url)
    health_url = base_url + "/health"
    publish_url = base_url + "/gossip/publish"

    last_error = ""
    health: dict[str, object] = {}
    publish: dict[str, object] = {}
    host_addrs: list[str] = []
    for attempt in range(1, max(1, int(args.retries)) + 1):
        try:
            host_addrs = _resolve_host(control_host)
            health = _http_json(health_url, timeout_s=float(args.timeout_s))
            publish = _http_json(
                publish_url,
                method="POST",
                payload={
                    "topic": "node_probe",
                    "payload": {
                        "probe_id": args.probe_id,
                        "status": "ok",
                        "timestamp_utc": _utc_now(),
                        "resolved_addresses": host_addrs,
                    },
                },
                timeout_s=float(args.timeout_s),
            )
            report = {
                "ok": True,
                "probe_id": args.probe_id,
                "control_url": control_url,
                "health_url": health_url,
                "publish_url": publish_url,
                "resolved_addresses": host_addrs,
                "health": health,
                "publish": publish,
                "timestamp_utc": _utc_now(),
            }
            output = str(args.output or "").strip()
            if output:
                _write_json(Path(output), report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, json.JSONDecodeError, socket.gaierror) as error:
            last_error = f"{type(error).__name__}:{error}"
            time.sleep(max(0.1, float(args.delay_s)))

    report = {
        "ok": False,
        "probe_id": args.probe_id,
        "control_url": control_url,
        "health_url": health_url,
        "publish_url": publish_url,
        "resolved_addresses": host_addrs,
        "error": last_error or "probe_failed",
        "timestamp_utc": _utc_now(),
    }
    output = str(args.output or "").strip()
    if output:
        _write_json(Path(output), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
