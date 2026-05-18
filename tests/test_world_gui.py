from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "world_gui.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("world_gui", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gui_renders_primary_actions() -> None:
    module = _load_module()
    html = module.render_page("Ready", 0, "")

    assert "Silicium World" in html
    assert "Computed tiles" in html
    assert "Tasks & results" in html
    assert 'value="up"' in html
    assert 'value="bootstrap"' in html
    assert 'value="chain_task"' in html
    assert "Chain task JSON" in html
    assert "No output yet." in html


def test_gui_base_world_args_are_cross_platform_strings() -> None:
    module = _load_module()
    args = module._base_world_args(
        {
            "node_id": ["croatia-1"],
            "seed": ["http://100.112.48.71:46001"],
            "advertise_host": ["100.100.81.27"],
            "roles": ["compute,verify,storage,audit,resource"],
            "solana": ["1"],
        }
    )

    assert args == [
        "--node-id",
        "croatia-1",
        "--seed",
        "http://100.112.48.71:46001",
        "--advertise-host",
        "100.100.81.27",
        "--roles",
        "compute,verify,storage,audit,resource",
        "--solana",
    ]


def test_gui_croatia_profile_sets_windows_defaults() -> None:
    module = _load_module()
    module.set_profile("croatia")

    html = module.render_page("Ready", 0, "")

    assert 'value="croatia-1"' in html
    assert 'value="100.100.81.27"' in html
    assert 'value="compute,verify,storage,audit,resource"' in html

    module.set_profile("france")


def test_gui_renders_json_as_css_panel() -> None:
    module = _load_module()

    html = module.render_output('{"count":2,"peers":[{"node_id":"croatia-1"}]}')

    assert "json-panel" in html
    assert "json-key" in html
    assert "croatia-1" in html
    assert "Raw JSON" in html


def test_gui_extracts_json_after_compose_noise() -> None:
    module = _load_module()

    parsed = module._extract_json('warning line\n{"ok":true,"reason":"peers_not_ready"}')

    assert parsed == {"ok": True, "reason": "peers_not_ready"}


def test_gui_collects_dashboard_from_state_files(tmp_path: Path) -> None:
    module = _load_module()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "requests").mkdir()
    (tmp_path / "node.france-1.peers.json").write_text(
        '{"count":1,"peers":[{"node_id":"france-1","roles":["compute"],"capacity":{"solana_enabled":true},"self":true}]}',
        encoding="utf-8",
    )
    (tmp_path / "node.france-1.heartbeat.json").write_text('{"solana_enabled":true}', encoding="utf-8")
    (tmp_path / "node.france-1.metrics.json").write_text('{"processed":2,"failed":0}', encoding="utf-8")
    (tmp_path / "tasks" / "demo.json").write_text(
        '{"task_id":"demo","status":"queued","required_roles":["compute"]}',
        encoding="utf-8",
    )
    (tmp_path / "result.demo.json").write_text(
        '{"task_id":"demo","success":true,"node_id":"croatia-1","tile_index":2,"result_hash":"sha256:abc"}',
        encoding="utf-8",
    )

    data = module.collect_dashboard(tmp_path)

    assert data["node_id"] == "france-1"
    assert data["peers"]["count"] == 1
    assert data["tasks"][0]["id"] == "demo"
    assert data["results"][0]["node"] == "croatia-1"
    assert data["tiles"][0]["index"] == 2


def test_gui_renders_tile_grid() -> None:
    module = _load_module()

    html = module.render_tiles([{"index": 1, "id": "tile-1", "node": "croatia-1", "hash": "sha256:abc"}])

    assert "tile-grid" in html
    assert "#1" in html
    assert "croatia-1" in html
