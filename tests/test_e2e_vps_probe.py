from __future__ import annotations

import json
import sys
from pathlib import Path

from tools import e2e_vps_probe


def test_control_host_uses_url_hostname() -> None:
    assert e2e_vps_probe._control_host("http://orchestrator:46100/gossip/publish") == "orchestrator"
    assert e2e_vps_probe._control_host("http://127.0.0.1:46100/gossip/publish") == "127.0.0.1"


def test_main_uses_hostname_from_control_url(monkeypatch, tmp_path: Path) -> None:
    resolved_hosts: list[str] = []
    requested_urls: list[tuple[str, dict[str, object]]] = []

    def fake_resolve_host(host: str) -> list[str]:
        resolved_hosts.append(host)
        return ["127.0.0.1"]

    def fake_http_json(url: str, **kwargs: object) -> dict[str, object]:
        requested_urls.append((url, kwargs))
        if url.endswith("/health"):
            return {"status": "ok"}
        if url.endswith("/gossip/publish"):
            payload = kwargs.get("payload")
            assert isinstance(payload, dict)
            assert payload["topic"] == "node_probe"
            assert payload["payload"]["resolved_addresses"] == ["127.0.0.1"]
            return {"published": True}
        raise AssertionError(url)

    monkeypatch.setattr(e2e_vps_probe, "_resolve_host", fake_resolve_host)
    monkeypatch.setattr(e2e_vps_probe, "_http_json", fake_http_json)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "e2e_vps_probe.py",
            "--control-url",
            "http://127.0.0.1:46100/gossip/publish",
            "--output",
            str(tmp_path / "probe.json"),
            "--retries",
            "1",
            "--delay-s",
            "0",
        ],
    )

    assert e2e_vps_probe.main() == 0
    assert resolved_hosts == ["127.0.0.1"]
    assert [url for url, _ in requested_urls] == [
        "http://127.0.0.1:46100/health",
        "http://127.0.0.1:46100/gossip/publish",
    ]
    report = json.loads((tmp_path / "probe.json").read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["resolved_addresses"] == ["127.0.0.1"]
