from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORLD_COMPOSE = REPO_ROOT / "infra" / "docker-compose.world.yml"
WORLD_DOCKERFILE = REPO_ROOT / "infra" / "docker" / "world-node.Dockerfile"
WORLD_ENTRYPOINT = REPO_ROOT / "infra" / "docker" / "world-node-entrypoint.sh"
SOLANA_TOOLS_DOCKERFILE = REPO_ROOT / "infra" / "docker" / "solana-tools.Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


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

    solana_service = services.get("silicium-world-solana")
    assert isinstance(solana_service, dict)
    build = solana_service.get("build")
    assert isinstance(build, dict)
    assert build.get("dockerfile") == "infra/docker/solana-tools.Dockerfile"
    assert solana_service.get("image") == "${SILICIUM_WORLD_SOLANA_IMAGE:-silicium/world-solana-tools:local}"
    assert solana_service.get("profiles") == ["tools"]
    solana_volumes = solana_service.get("volumes")
    assert isinstance(solana_volumes, list)
    assert "${SILICIUM_WORLD_STATE_DIR:-../.silicium-world}:/state:Z" in solana_volumes


def test_world_dockerfile_installs_node_and_runs_silicium_cli() -> None:
    text = WORLD_DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM python:3.12-slim-bookworm" in text
    assert "nodejs" in text
    assert "npm" in text
    assert "openssl" in text
    assert "world-node-entrypoint.sh" in text


def test_world_entrypoint_installs_missing_solana_js_deps() -> None:
    text = WORLD_ENTRYPOINT.read_text(encoding="utf-8")
    assert "npm install --include=dev --no-audit --no-fund" in text
    assert 'SOLANA_LAYER_DIR="/workspace/solana-layer"' in text
    assert 'node_modules/@coral-xyz/anchor' in text
    assert "exec python3 /workspace/silicium" in text


def test_solana_tools_dockerfile_installs_ca_and_solana_cli() -> None:
    text = SOLANA_TOOLS_DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM python:3.12-slim-bookworm" in text
    assert "ca-certificates" in text
    assert "curl" in text
    assert "https://release.anza.xyz/stable/install" in text
    assert 'ENTRYPOINT ["/bin/sh", "-lc"]' in text


def test_world_dockerignore_keeps_build_context_minimal() -> None:
    text = DOCKERIGNORE.read_text(encoding="utf-8")
    assert "**" in text
    assert "!infra/docker/world-node.Dockerfile" in text
    assert "!infra/docker/world-node-entrypoint.sh" in text
    assert "!infra/docker/solana-tools.Dockerfile" in text
