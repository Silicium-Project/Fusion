# Development miniworkers

This separate Compose project creates 20 to 24 dev-only worker identities on
the VPS. They use an isolated bridge network, have no published ports, accept
only the raytracer workload, and are capped at 0.10 vCPU and 160 MiB each.
Each peer has a dedicated named `/data` volume, so its libp2p identity and
taskbook persist across container and Compose recreation. Startup also creates
one Solana Devnet keypair per volume at `/data/solana-wallet.json` (mode 0600);
the container logs only its public address. Recreating a container preserves
that address and its key. These wallets are Devnet-only and are not funded or
registered with the Solana program by Compose.

These containers increase test concurrency on one host. They are not separate
machines and do not add host-level availability.

On the VPS, copy `deploy/env/dev-miniworkers.env.example` to
`deploy/env/dev-miniworkers.env`, then run:

```sh
sudo ./deploy/linux/manage-dev-miniworkers.sh up
sudo ./deploy/linux/manage-dev-miniworkers.sh status
sudo ./deploy/linux/manage-dev-miniworkers.sh logs
sudo ./deploy/linux/manage-dev-miniworkers.sh down
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
