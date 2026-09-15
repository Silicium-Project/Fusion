# Silicium deployment

This folder contains a first production-oriented VPS deployment for the public
site.

The intended operating model is VPS-first: GitHub acts as source control and
trigger surface, while the actual deploy/test path runs on the VPS or on a
self-hosted runner attached to the VPS.

## Release channels

The channel contract lives in `deploy/release/channels.json`:

- `dev` follows the `dev` branch, uses `/opt/silicium-dev`,
  `/etc/silicium-dev`, `/var/lib/silicium-dev` and Compose project
  `silicium-dev` by default. On a shared VPS it uses host ports `46200`,
  `8180`, `3300`, `5274`, `9191` and the private WireGuard ingress
  `10.77.0.1:8443`, with channel-suffixed systemd units such as
  `silicium-orchestrator-dev.service`;
- `prod` follows `main` and `v*` tags and keeps the legacy production paths
  `/opt/silicium`, `/etc/silicium`, `/var/lib/silicium` and project `silicium`.

Use an explicit channel for a development deployment. The bootstrap creates
the isolated WireGuard server, dev secrets, PostgreSQL credentials and a TLS
certificate signed by the dev CA without reading production configuration. The
installer and Compose scripts then propagate the channel to the FrontEnd,
BackEnd, orchestrator, update manifest and Network peer identity:

```bash
sudo SILICIUM_RELEASE_CHANNEL=dev \
  bash deploy/linux/prepare-dev-config.sh /opt/silicium-dev
sudo SILICIUM_RELEASE_CHANNEL=dev \
  bash deploy/linux/install-services.sh /opt/silicium-dev
sudo SILICIUM_RELEASE_CHANNEL=dev \
  bash deploy/compose/deploy.sh /opt/silicium-dev
```

The guarded `.github/workflows/deploy-dev-vps.yml` workflow runs the same
sequence over the configured VPS SSH connection. Its dev ingress is private to
the WireGuard network: `https://10.77.0.1:8443`. The generated CA certificate
is at `/var/lib/silicium-dev/tls/dev-ca.crt.pem`; install that certificate on
an authorized team device before opening the site in a browser.

### Development VPN

The dev deployment provisions `wg0` with server address `10.77.0.1/24` and
listens for WireGuard clients on UDP `51820`. UFW permits the VPN handshake,
the dev web ingress and the orchestrator/worker control-plane ports only from
`10.77.0.0/24`; the production ingress remains separate. If an OVH cloud
firewall or security group is enabled, allow inbound UDP `51820` there too.

Create and revoke named internal-team peers on the VPS without committing
private keys to Git:

```bash
sudo bash deploy/vpn/manage-peer.sh /opt/silicium-dev add alice
sudo cat /etc/wireguard/silicium-dev-peers/alice.conf
sudo bash deploy/vpn/manage-peer.sh /opt/silicium-dev list
sudo bash deploy/vpn/manage-peer.sh /opt/silicium-dev revoke alice
```

Copy a generated client configuration securely into the WireGuard application
on the team device. `rotate <name>` revokes the old key and creates a new
configuration for that peer. Client `AllowedIPs` is limited to `10.77.0.0/24`;
the VPN is not used as an Internet gateway.

Production remains explicit in CI and is also the safe default for the
production paths:

```bash
sudo SILICIUM_RELEASE_CHANNEL=prod bash deploy/linux/install-services.sh /opt/silicium
sudo SILICIUM_RELEASE_CHANNEL=prod bash deploy/compose/deploy.sh /opt/silicium
```

Development pushes publish a prerelease through `.github/workflows/release-dev.yml`.
Promotion is a reviewed merge from `dev` to `main`; the production deployment
workflow does not run from `dev`.

The canonical GitHub-visible pipeline is split into three stages:

1. `build.yml` produces the Linux bundles on the VPS runner.
2. `test.yml` runs the web stack, Network core, Docker E2E, and P2P smoke
   checks on the VPS runner.
3. `deploy-vps.yml` is the production `Deploy` stage.

Recommended first public setup:

1. One Linux VPS hosts:
   - Nuxt frontend on `127.0.0.1:3000`
   - Go backend on `127.0.0.1:8080`
   - Devnet dashboard on `127.0.0.1:5174` for local/admin inspection only
   - Silicium orchestrator on host port `46100`, behind the HTTPS `/orchestrator/` route
2. Remote worker/verifier machines connect to the HTTPS orchestrator rendezvous URL.
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
- labels: `self-hosted,fusion-linux,fusion-bootstrap`
- directory: `/opt/github-runner`

Use a fresh GitHub runner registration token. The script downloads the current
runner release, configures the service, and starts it on the VPS.
It also adds the runner user to the `docker` group so compose-based CI jobs can
reach the daemon socket.

The first Fusion gate also provisions repo-scoped VPS runners for `BackEnd` and
`FrontEnd` under `/opt/github-runner-backend` and `/opt/github-runner-frontend`.
The publication token must therefore be able to create repository runner
registration tokens for those two repositories.

Copy and edit env files:

```bash
sudo cp deploy/env/backend.example.env /etc/silicium/backend.env
sudo cp deploy/env/frontend.example.env /etc/silicium/frontend.env
sudo cp deploy/env/orchestrator.example.env /etc/silicium/orchestrator.env
sudo nano /etc/silicium/backend.env
sudo nano /etc/silicium/frontend.env
sudo nano /etc/silicium/orchestrator.env
```

Build the backend binary and install the host-side control-plane services:

```bash
sudo bash deploy/linux/build-site.sh /opt/silicium
sudo bash deploy/linux/install-services.sh /opt/silicium
```

The public web/API/dashboard processes are owned only by Docker Compose:

```bash
sudo systemctl enable --now silicium-orchestrator silicium-experiment-api silicium-update-manifest.timer
sudo bash deploy/compose/deploy.sh /opt/silicium
```

Do not reinstall or enable the removed `silicium-backend`,
`silicium-frontend`, or `silicium-dashboard` systemd units. They are legacy
duplicates and would compete with Compose for ports 8080, 3000, and 5174.

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

## Node installers

The deployment workflow builds and publishes the Windows and Linux node
artifacts both to the GitHub Release and to the persistent VPS directory. The
public site uses these stable paths:

```text
/downloads/silicium-node-windows.exe
/downloads/silicium-node-windows-dev.exe
/downloads/silicium-node-linux.AppImage
/downloads/silicium-node-linux.deb
/downloads/silicium-node-linux.rpm
/downloads/silicium-node-linux-dev.AppImage
/downloads/silicium-node-linux-dev.deb
/downloads/silicium-node-linux-dev.rpm
```

The `.deb` is the native installation path on Debian/Ubuntu:

```bash
sudo apt install ./silicium-node-linux-dev.deb
```

The `.rpm` is the native installation path on Fedora/RHEL:

```bash
sudo dnf install ./silicium-node-linux-dev.rpm
```

Production also exposes native package repositories:

```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://vps-910c1dbc.vps.ovh.net/downloads/apt/silicium-packages.asc \
  | sudo gpg --dearmor -o /etc/apt/keyrings/silicium-prod.gpg
echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/silicium-prod.gpg] https://vps-910c1dbc.vps.ovh.net/downloads/apt stable main' \
  | sudo tee /etc/apt/sources.list.d/silicium-node.list >/dev/null
sudo apt update && sudo apt install silicium-node

sudo install -d -m 0755 /etc/yum.repos.d
sudo curl -fsSL https://vps-910c1dbc.vps.ovh.net/downloads/rpm/silicium-node.repo \
  -o /etc/yum.repos.d/silicium-node.repo
sudo dnf makecache && sudo dnf install silicium-node
```

The development repository uses the same paths behind WireGuard at
`https://10.77.0.1:8443/downloads` and the APT suite `dev`.

An AppImage downloaded from a browser must be made executable once with
`chmod +x silicium-node-linux-dev.AppImage` before it is launched.

Verify every public asset after a deployment:

```bash
for artifact in \
  silicium-node-windows.exe \
  silicium-node-windows-dev.exe \
  silicium-node-linux.AppImage \
  silicium-node-linux.deb \
  silicium-node-linux.rpm \
  silicium-node-linux-dev.AppImage \
  silicium-node-linux-dev.deb \
  silicium-node-linux-dev.rpm; do
  curl -fI "https://vps-910c1dbc.vps.ovh.net/downloads/$artifact"
done
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

The backend reaches the host-side orchestrator and experiment/MCP RPC event
socket through `host.docker.internal`; the Compose deployment resolves that
name to the gateway of the channel-specific Docker network. The reverse proxy
uses the same isolated bridge and reaches the host-side orchestrator through
that gateway. The HTTP experiment API and its control RPC remain private to
the host; only the event socket needed by the backend is reachable from the
backend container. The dev proxy itself is bound to `10.77.0.1:8443`, and UFW
permits it only to WireGuard clients in `10.77.0.0/24`.

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

`/.github/workflows/deploy-vps.yml` is the canonical production `Deploy`
workflow. It deploys every push to `main` that changes the site, backend,
network, or deployment files, and also deploys every pushed release tag
matching `v*` (version rollout). It can also be started from the GitHub
Actions interface with `Run workflow`, optionally with a custom deploy ref.
Configure these repository secrets before the first run:

- `VPS_HOST`: public VPS hostname or IP;
- `VPS_SSH_KEY`: private Ed25519 key authorized on the VPS;
- `VPS_KNOWN_HOSTS`: pinned `known_hosts` entry for the VPS;

The workflow dispatch form provides optional runtime overrides:

- `vps_user`: SSH deployment user (default `ubuntu`);
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

The Windows packaging job runs on GitHub-hosted `windows-latest` capacity. It
does not require a repository self-hosted Windows runner or a runner-listing
token. The repository or organization must have sufficient Actions minutes or
an enabled Actions budget for private-repository hosted execution.

The deployment user must be able to run the Compose deployment script through
`sudo` without an interactive password prompt. The workflow performs a
ref checkout, updates all submodules, rebuilds the containers, and starts
the stack. For every deployment, the workflow writes a release marker at
`/var/lib/silicium/releases/current.env` with deployed version, channel, build,
and deploy ref. The Windows installers are built on `windows-latest`, staged on
the VPS, and installed under `/var/lib/silicium/downloads`.

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
bash deploy/linux/start-node.sh worker-1 compute 46101 https://vps-910c1dbc.vps.ovh.net/orchestrator WORKER_PUBLIC_IP demo-mesh 120
```

On a verifier:

```bash
bash deploy/linux/start-node.sh verifier-1 verify 46102 https://vps-910c1dbc.vps.ovh.net/orchestrator VERIFIER_PUBLIC_IP demo-mesh 90
```
