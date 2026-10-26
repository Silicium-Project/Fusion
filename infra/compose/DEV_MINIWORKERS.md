# Development miniworkers

This separate Compose project creates 20 to 24 dev-only worker identities on
the VPS. They use an isolated bridge network, have no published ports, accept
raytracer and chunked SHA-256 workloads, and are capped at 0.05 vCPU and
256 MiB each.
Each peer has a dedicated named `/data` volume, so its libp2p identity and
taskbook persist across container and Compose recreation. Startup also creates
one Solana Devnet keypair per volume at `/data/solana-wallet.json` (mode 0600);
the container logs only its public address. Recreating a container preserves
that address and its key. These wallets are Devnet-only and are not funded or
registered with the Solana program by Compose.

These containers increase test concurrency on one host. They are not separate
machines and do not add host-level availability.

To link all 20 workers to the signed-in website account, open **Espace
worker → Associer les 20 miniworkers**. The verified account wallet is bound to
the request. The backend writes a distinct short-lived authorization into each
worker's private mount; each container signs it with its persistent identity
and calls the path-limited relay. The user never downloads or manually copies
a code or website session token to the VPS. A worker appears under the account
after the backend verifies its identity and the node reports it to the
orchestrator. The page shows linked devices separately from miniworkers
currently visible on the network.

The single-device code flow is for a separately installed desktop Silicium
Node. Do not use `manage-dev-miniworkers.sh pair` for the pool-link button; that
legacy command accepts a manually supplied JSON file and is not part of the
website flow.

The dev bootstrap keeps the worker settings in `/etc/silicium-dev/miniworkers.env`,
outside the Git checkout so a deployment cannot delete them. It creates that
file from `infra/env/dev-miniworkers.env.example` on first setup. Run:

```sh
sudo ./infra/linux/manage-dev-miniworkers.sh up
sudo ./infra/linux/manage-dev-miniworkers.sh status
sudo ./infra/linux/manage-dev-miniworkers.sh logs
sudo ./infra/linux/manage-dev-miniworkers.sh down
```

Set `SILICIUM_DEV_MINIWORKERS=24` in the env file, then run the `scale`
command to activate all 24 defined peers. `down` leaves the peer volumes in
place; removing them requires an explicit Docker volume deletion.

The worker bridge is `172.23.0.0/24` with the VPS host gateway at
`172.23.0.1`. The host firewall must allow that subnet to reach only the dev
orchestrator's TCP/UDP port `46201`.

The Docker volumes hold signing keys and must remain attached to their named
worker. Back them up only as encrypted secrets; deleting a worker volume
permanently loses that Devnet wallet.
