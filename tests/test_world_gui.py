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
    assert 'value="up"' in html
    assert 'value="bootstrap"' in html
    assert 'value="chain_task"' in html
    assert "Chain task JSON" in html


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
