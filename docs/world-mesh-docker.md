# World Mesh Docker

This compose file packages the role-aware Silicium mesh node in a small Python image with `openssl` preinstalled.
It also exposes an optional Solana CLI helper service so the wallet/keypair flow can stay containerized and portable across hosts.
You do not need a host-level Solana installation to create the wallet, request Devnet funds, or register a worker.
If the mounted repository does not already contain `solana-layer/node_modules`, the world node will install the missing JS dependencies automatically on first boot.

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

## Portable Solana wallet flow

The easiest path is to use the helper wrapper:

```bash
python3 tools/world_solana_docker.py init-wallet --force
python3 tools/world_solana_docker.py pubkey
python3 tools/world_solana_docker.py balance
python3 tools/world_solana_docker.py airdrop 2
python3 tools/world_solana_docker.py bootstrap-worker
```

All of those commands run through Docker Compose and keep the keypair under the world state volume.
The first invocation will build the dedicated Solana tools image with CA certificates and the Solana CLI bundled inside it.

`init-wallet --force` replaces the existing world wallet, so only use `--force` when you intentionally want a fresh keypair.

If you want the raw Docker Compose equivalents, they are below.

To keep the Devnet wallet inside Docker-managed state instead of relying on host tooling:

Create the wallet:

```bash
docker compose -f infra/docker-compose.world.yml --profile tools run --rm \
  --entrypoint solana-keygen \
  silicium-world-solana \
  new --no-bip39-passphrase --force --outfile /state/solana/id.json
```

Read the public key:

```bash
docker compose -f infra/docker-compose.world.yml --profile tools run --rm \
  --entrypoint solana-keygen \
  silicium-world-solana \
  pubkey /state/solana/id.json
```

Check balance:

```bash
docker compose -f infra/docker-compose.world.yml --profile tools run --rm \
  --entrypoint solana \
  silicium-world-solana \
  balance --url https://api.devnet.solana.com --keypair /state/solana/id.json
```

Request Devnet SOL:

```bash
docker compose -f infra/docker-compose.world.yml --profile tools run --rm \
  --entrypoint solana \
  silicium-world-solana \
  airdrop 2 --url https://api.devnet.solana.com $(docker compose -f infra/docker-compose.world.yml --profile tools run --rm --entrypoint solana-keygen silicium-world-solana pubkey /state/solana/id.json)
```

The wallet lives under:

```text
../.silicium-world/solana/id.json
```

That same file is mounted into the world node container at:

```text
/state/solana/id.json
```

So `bootstrap-worker` and on-chain task execution can reuse it directly once the wallet is funded.

The Python helper above is just a thin wrapper over those containerized commands, so teammates on Linux and Windows do not need `solana` or `solana-keygen` installed on the host.
