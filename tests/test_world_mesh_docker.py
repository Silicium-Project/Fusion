from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORLD_COMPOSE = REPO_ROOT / "infra" / "docker-compose.world.yml"
WORLD_DOCKERFILE = REPO_ROOT / "infra" / "docker" / "world-node.Dockerfile"


def test_world_compose_exposes_world_node_service() -> None:
    data = yaml.safe_load(WORLD_COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    services = data.get("services")
    assert isinstance(services, dict)
    service = services.get("silicium-world-node")
    assert isinstance(service, dict)

    command = service.get("command")
    assert isinstance(command, list)
    assert "--world" in command
    assert "--world-name" in command
    assert "--world-seeds" in command

    ports = service.get("ports")
    assert isinstance(ports, list)
    assert "${SILICIUM_WORLD_GOSSIP_PORT:-46000}:46000/udp" in ports
    assert "${SILICIUM_WORLD_HTTP_PORT:-46001}:46001/tcp" in ports

    environment = service.get("environment")
    assert isinstance(environment, dict)
    assert "SILICIUM_WORLD_ADVERTISE_HOST" in environment
    assert "SILICIUM_SOLANA_PROGRAM_ID" in environment


def test_world_dockerfile_installs_openssl_and_runs_silicium_cli() -> None:
    text = WORLD_DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM python:3.12-slim-bookworm" in text
    assert "openssl" in text
    assert 'ENTRYPOINT ["python3", "/workspace/silicium"]' in text
