# Silicium deployment

This folder contains a first production-oriented VPS deployment for the public
site.

The intended operating model is VPS-first: GitHub acts as source control and
trigger surface, while the actual deploy/test path runs on the VPS or on a
self-hosted runner attached to the VPS.

Recommended first public setup:

1. One Linux VPS hosts:
   - Nuxt frontend on `127.0.0.1:3000`
   - Go backend on `127.0.0.1:8080`
   - Devnet dashboard on `127.0.0.1:5174` for local/admin inspection only
   - Silicium orchestrator on public port `46100`
2. Remote worker/verifier machines connect to the VPS orchestrator.
3. Nginx exposes:
   - `https://silicium.example.com`
   - `https://api.silicium.example.com`
4. The Devnet dashboard is not exposed publicly by default. Keep it local or put
   it behind authentication before exposing it.

## VPS install

Clone the repository on the VPS, then run:

```bash
sudo bash deploy/linux/install-vps.sh /opt/silicium
```

If you want this VPS to also execute GitHub Actions jobs for the `fusion-linux`
label, enable the optional self-hosted runner bootstrap during the VPS install.
This is the preferred mode for the deployment and validation workflows:

```bash
sudo SILICIUM_INSTALL_GITHUB_ACTIONS_RUNNER=1 \
  SILICIUM_GHA_RUNNER_URL=https://github.com/Silicium-Project \
  SILICIUM_GHA_RUNNER_TOKEN=ghs_... \
  bash deploy/linux/install-vps.sh /opt/silicium
```

Default runner settings:

- name: `fusion-vps`
- user: `github-runner`
- labels: `self-hosted,fusion-linux`
- directory: `/opt/github-runner`

Use a fresh GitHub runner registration token. The script downloads the current
runner release, configures the service, and starts it on the VPS.
It also adds the runner user to the `docker` group so compose-based CI jobs can
reach the daemon socket.

Copy and edit env files:

```bash
sudo cp deploy/env/backend.example.env /etc/silicium/backend.env
sudo cp deploy/env/frontend.example.env /etc/silicium/frontend.env
sudo cp deploy/env/orchestrator.example.env /etc/silicium/orchestrator.env
sudo nano /etc/silicium/backend.env
sudo nano /etc/silicium/frontend.env
sudo nano /etc/silicium/orchestrator.env
```

Build and install services:

```bash
sudo bash deploy/linux/build-site.sh /opt/silicium
sudo bash deploy/linux/install-services.sh /opt/silicium
```

Enable services:

```bash
sudo systemctl enable --now silicium-backend silicium-frontend silicium-dashboard silicium-orchestrator
```

Install Nginx config after replacing domains:

```bash
sudo cp deploy/nginx/silicium.conf /etc/nginx/sites-available/silicium.conf
sudo nano /etc/nginx/sites-available/silicium.conf
sudo ln -s /etc/nginx/sites-available/silicium.conf /etc/nginx/sites-enabled/silicium.conf
sudo nginx -t
sudo systemctl reload nginx
```

For HTTPS, use certbot:

```bash
sudo certbot --nginx -d silicium.example.com -d api.silicium.example.com
```

## Windows desktop application

The frontend downloads the installer from the latest GitHub Release asset:

```text
https://github.com/Silicium-Project/Fusion/releases/latest/download/Silicium-Node-0.2.1-x64-setup.exe
```

Publish a new installer without copying binaries to the VPS:

```bash
gh release create v0.2.1 \
  "Silicium Node_0.2.1_x64-setup.exe" \
  --repo Silicium-Project/Fusion \
  --title "Silicium Node 0.2.1" \
  --notes "Automatic ICE P2P desktop node."
```

Verify the public asset:

```bash
curl -I https://github.com/Silicium-Project/Fusion/releases/latest/download/Silicium-Node-0.2.1-x64-setup.exe
```

## Containerized VPS deployment

The production services run with Docker Compose. PostgreSQL uses the bind mount
`/var/lib/silicium/postgres`; the legacy PostgreSQL data is migrated with a
verified logical dump and is never deleted automatically.

Prepare the VPS once. The installer also installs `sqlite3` for converting the
legacy database:

```bash
sudo bash deploy/linux/install-vps.sh /opt/silicium
sudo test -e /etc/silicium/compose.env || sudo cp deploy/env/compose.example.env /etc/silicium/compose.env
sudo nano /etc/silicium/compose.env
sudo bash deploy/linux/migrate-postgres-to-compose.sh /opt/silicium
```

Keep the existing `/etc/silicium/backend.env` and its secrets. Compose injects
the container PostgreSQL URL at runtime; do not replace the backend environment
file with the example file.

For the current legacy SQLite installation, the migration detects
`/var/lib/silicium/site/silicium.db`, checks its integrity, backs it up, creates
the PostgreSQL schema, and imports the `users` table. After the PostgreSQL
backend is running and the row count is verified, the active SQLite file and
its environment variables are removed. A timestamped recovery copy remains
outside the runtime data path. For a legacy PostgreSQL
installation, inspect the existing databases and set the source name without
changing the old data:

```bash
sudo bash deploy/linux/install-vps.sh /opt/silicium
sudo -u postgres psql -lqt
sudo nano /etc/silicium/compose.env
```

Set `SOURCE_POSTGRES_DB` to the existing database, choose a new container
password, and keep the database backup produced by the migration. Do not run
`docker compose down -v`: that would remove container volumes.

The migration creates a timestamped backup under
`/var/lib/silicium/backups/postgres`, refuses a non-empty new data directory,
checks the imported row count, and only then starts the complete container
stack. The legacy PostgreSQL data directory is retained; SQLite is removed from
the active runtime after a successful import.

After the one-time migration, pushes to `main` run:

```bash
sudo bash /opt/silicium/deploy/compose/deploy.sh /opt/silicium
```

Do not run the migration script again for normal deployments.

## Automatic VPS deployment

`/.github/workflows/deploy-vps.yml` deploys every push to `main` that changes
the site, backend, network, or deployment files, and also deploys every pushed
release tag matching `v*` (version rollout). It can also be started from
the GitHub Actions interface with `Run workflow`, optionally with a custom
deploy ref. Configure these repository secrets before the first run:

- `VPS_HOST`: public VPS hostname or IP;
- `VPS_SSH_KEY`: private Ed25519 key authorized on the VPS;
- `VPS_KNOWN_HOSTS`: pinned `known_hosts` entry for the VPS;

The workflow dispatch form provides optional runtime overrides:

- `vps_user`: SSH deployment user (default `luis`);
- `vps_port`: SSH port (default `22`);
- `vps_root`: checkout path on VPS (default `/opt/silicium`).

The workflow uses a private GitHub App instead of a personal access token. Store
its client ID as the repository secret `SILICIUM_DEPLOY_APP_CLIENT_ID` and
its private key as the repository secret `SILICIUM_DEPLOY_APP_PRIVATE_KEY`.
Install the App on `Fusion`, `BackEnd`, `FrontEnd`, and `Network` with only
`Contents: Read-only` permission. The submodule sync workflow uses that token to
read the private repositories. To publish Fusion's exact gitlinks, configure
either `SILICIUM_SYNC_PUSH_TOKEN` with a token that has write access on
`Fusion`, or `SILICIUM_SYNC_DEPLOY_KEY` with an SSH deploy key allowed to push
to `main`. Optionally provide `SILICIUM_SYNC_DEPLOY_KNOWN_HOSTS` to pin the SSH
host key instead of relying on `ssh-keyscan`. If no dedicated publication secret
is configured, the workflow stops with an explicit error. Tokens are revoked
when their job completes.

The deployment user must be able to run the Compose deployment script through
`sudo` without an interactive password prompt. The workflow performs a
ref checkout, updates all submodules, rebuilds the containers, and starts
the stack. For every deployment, the workflow writes a release marker at
`/var/lib/silicium/releases/current.env` with deployed version, channel, build,
and deploy ref. The Windows installer is served directly from the GitHub
Release and is not copied to the VPS.

GitHub should be treated as the orchestrator and audit trail, not as the place
where the production path executes. Any workflow that must touch production
state should run on the VPS self-hosted runner or over SSH into the VPS.

After each deployment, CI/CD runs `deploy/linux/post-deploy-check.sh` on the
VPS. This validates Compose service state, local health endpoints, node service
state, and release marker presence before marking the workflow as successful.

For version rollouts (`v*` tags), CI/CD pushes the exact tagged revision to the
VPS and restarts `silicium-node.service` after Compose deployment to ensure the
node stack and VPS move together at each version.

## Manual rollback workflow

Use `/.github/workflows/rollback-vps.yml` from GitHub Actions with:

- `deploy_ref`: required tag, branch, or SHA to restore;
- optional labels `release_version` and `release_channel` for release marker
   tracking;
- optional runtime overrides `vps_user`, `vps_port`, and `vps_root`.

The rollback workflow performs the same submodule synchronization and
post-deploy checks as standard deployment, then rewrites
`/var/lib/silicium/releases/current.env` to the selected rollback reference.

## Remote workers

On a worker machine, install the repo and raytracer runtime, then start:

```bash
bash deploy/linux/start-node.sh worker-1 compute 46101 http://ORCHESTRATOR_PUBLIC_IP:46100 WORKER_PUBLIC_IP demo-mesh 120
```

On a verifier:

```bash
bash deploy/linux/start-node.sh verifier-1 verify 46102 http://ORCHESTRATOR_PUBLIC_IP:46100 VERIFIER_PUBLIC_IP demo-mesh 90
```
