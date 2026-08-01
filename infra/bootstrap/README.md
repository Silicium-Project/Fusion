# Bootstrap VPS

This compose file starts the Silicium bootstrap node on a VPS.

## Ports

- `4001/tcp` and `4001/udp` for libp2p transport
- `9092/tcp` for the local control API and healthcheck

## Host preparation

```bash
sudo ufw allow 4001/tcp
sudo ufw allow 4001/udp
sudo ufw allow 9092/tcp
sudo ufw reload
```

## Start

```bash
docker compose -f infra/bootstrap/docker-compose.yml up -d --build
```

## Notes

- Mount a persistent volume for `/data` if you later add identity or cache files.
- Override `SILICIUM_BOOTSTRAP_PEERS` with the external peer list when the DHT ring expands.
- Keep TLS termination at the VPS reverse proxy layer if the node is exposed publicly.

