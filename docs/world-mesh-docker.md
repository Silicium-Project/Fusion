# World Mesh Docker

This compose file packages the role-aware Silicium mesh node in a small Python image with `openssl` preinstalled.

## Start

From the repository root:

```bash
docker compose -f infra/docker-compose.world.yml up --build
```

## Recommended environment

```bash
export SILICIUM_WORLD_NAME=team-europe
export SILICIUM_NODE_ID=france-1
export SILICIUM_WORLD_SEEDS=http://SEED_HOST_OR_IP:46001
export SILICIUM_WORLD_ADVERTISE_HOST=YOUR_PUBLIC_OR_TAILSCALE_IP
```

Then:

```bash
docker compose -f infra/docker-compose.world.yml up --build
```

## Ports

- `46000/udp`: gossip
- `46001/tcp`: peer HTTP and discovery

Override host ports if needed:

```bash
export SILICIUM_WORLD_GOSSIP_PORT=47000
export SILICIUM_WORLD_HTTP_PORT=47001
```

## Persistent state

By default the compose file stores state in:

```text
../.silicium-world
```

Override it with:

```bash
export SILICIUM_WORLD_STATE_DIR=/absolute/path/to/state
```

## Two-machine example

Machine 1:

```bash
export SILICIUM_WORLD_NAME=team-europe
export SILICIUM_NODE_ID=france-1
export SILICIUM_WORLD_SEEDS=http://100.64.1.10:46001
export SILICIUM_WORLD_ADVERTISE_HOST=100.64.1.10
docker compose -f infra/docker-compose.world.yml up --build
```

Machine 2:

```bash
export SILICIUM_WORLD_NAME=team-europe
export SILICIUM_NODE_ID=croatia-1
export SILICIUM_WORLD_SEEDS=http://100.64.1.10:46001
export SILICIUM_WORLD_ADVERTISE_HOST=100.64.1.11
docker compose -f infra/docker-compose.world.yml up --build
```

Tailscale is the easiest way to make this reliable across countries.
