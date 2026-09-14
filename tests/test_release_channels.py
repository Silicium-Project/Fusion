from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deploy.release.channel import infer_from_ref, metadata, normalize


def test_release_channels_are_explicit_and_isolated() -> None:
    dev = metadata("dev")
    prod = metadata("prod")

    assert dev["branch"] == "dev"
    assert dev["node_update_channel"] == "dev"
    assert dev["deployment_root"] != prod["deployment_root"]
    assert dev["data_dir"] != prod["data_dir"]
    assert dev["compose_project"] != prod["compose_project"]
    assert dev["service_suffix"] == "-dev"
    assert dev["orchestrator_port"] != prod["orchestrator_port"]
    assert dev["proxy_https_port"] != prod["proxy_https_port"]
    assert dev["backend_network_name"] != prod["backend_network_name"]
    assert dev["vpn_interface"] == "wg0"
    assert dev["vpn_network"] == "10.77.0.0/24"
    assert dev["vpn_server_address"] == "10.77.0.1"
    assert dev["vpn_listen_port"] == 51820
    assert dev["vpn_proxy_bind_address"] == dev["proxy_bind_address"]
    assert dev["public_base_url"] == "https://10.77.0.1:8443"
    assert "vpn_interface" not in prod


def test_channel_inference_keeps_main_and_tags_production_only() -> None:
    assert infer_from_ref("dev") == "dev"
    assert infer_from_ref("refs/heads/dev") == "dev"
    assert infer_from_ref("main") == "prod"
    assert infer_from_ref("refs/tags/v1.2.3") == "prod"


def test_normalize_rejects_cross_channel_values() -> None:
    assert normalize(" DEV ") == "dev"
    try:
        normalize("staging")
    except ValueError as error:
        assert "unsupported release channel" in str(error)
    else:
        raise AssertionError("an unknown channel must be rejected")
