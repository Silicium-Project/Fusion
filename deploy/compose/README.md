# Containerized production stack

This stack runs PostgreSQL, the Go backend, the Nuxt frontend, the dashboard,
the network orchestrator, and the reverse proxy in containers.

The PostgreSQL data directory is a host bind mount at
`/var/lib/silicium/postgres`. The migration script never removes an existing
database directory and writes a timestamped logical backup before the cutover.

Start the stack with:

```bash
sudo docker compose --env-file /etc/silicium/compose.env \
  -f /opt/silicium/deploy/compose/docker-compose.yml up -d --build
```
