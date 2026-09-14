from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_wireguard_scripts_are_executable_and_guarded() -> None:
    for relative_path in ("deploy/vpn/install-server.sh", "deploy/vpn/manage-peer.sh"):
        path = ROOT / relative_path
        assert path.is_file(), relative_path
        assert path.stat().st_mode & 0o111, relative_path
        source = path.read_text(encoding="utf-8")
        assert "SILICIUM_RELEASE_CHANNEL" in source
        assert "dev" in source
        assert "/etc/wireguard" in source


def test_dev_bootstrap_provisions_vpn_before_private_ingress() -> None:
    bootstrap = (ROOT / "deploy/linux/prepare-dev-config.sh").read_text(encoding="utf-8")
    compose_deploy = (ROOT / "deploy/compose/deploy.sh").read_text(encoding="utf-8")
    post_check = (ROOT / "deploy/linux/post-deploy-check.sh").read_text(encoding="utf-8")

    assert "deploy/vpn/install-server.sh" in bootstrap
    assert "SILICIUM_PROXY_BIND_ADDRESS \"$VPN_PROXY_BIND_ADDRESS\"" in bootstrap
    assert "VPN_ORCHESTRATOR_PORT" in (ROOT / "deploy/vpn/install-server.sh").read_text(encoding="utf-8")
    assert "vpn_server_address" in compose_deploy
    assert "The dev VPN address" in compose_deploy
    assert "wg-quick@${channel_vpn_interface}.service" in post_check
    assert "public_route_target=\"$channel_vpn_server_address\"" in post_check


def test_compose_keeps_internal_services_off_the_vpn_ingress() -> None:
    compose = (ROOT / "deploy/compose/docker-compose.yml").read_text(encoding="utf-8")
    assert "${SILICIUM_PROXY_BIND_ADDRESS:-0.0.0.0}:${SILICIUM_PROXY_HTTPS_PORT:-443}:443" in compose
    assert "${SILICIUM_HOST_GATEWAY:-host-gateway}" in compose
