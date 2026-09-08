# Containerized production stack

This stack runs PostgreSQL, the Go backend, the Nuxt frontend, the dashboard,
the reputation bridge, TURN, and the reverse proxy in containers. The network
orchestrator and authenticated experiment/MCP API remain host-side systemd
services.

The PostgreSQL data directory is a host bind mount at
`/var/lib/silicium/postgres`. The migration script never removes an existing
database directory and writes a timestamped logical backup before the cutover.

Start the stack with:

```bash
sudo docker compose --env-file /etc/silicium/compose.env \
  -f /opt/silicium/deploy/compose/docker-compose.yml up -d --build
```

For the complete deployment, run `deploy.sh`; it also refreshes the signed
desktop update manifest and recreates the proxy after the application services.
