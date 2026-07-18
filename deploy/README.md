# Silicium deployment

This folder contains a first production-oriented VPS deployment for the public
site.

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

Build and sign the Windows installer, then upload it to the persistent download
directory using the exact public filename expected by the frontend:

```bash
scp "Silicium Node_0.2.0_x64-setup.exe" USER@VPS:/tmp/silicium-node-windows.exe
ssh USER@VPS "sudo install -o root -g root -m 0644 /tmp/silicium-node-windows.exe /var/lib/silicium/downloads/silicium-node-windows.exe"
```

The frontend variable must remain:

```text
NUXT_PUBLIC_NODE_APP_WINDOWS_URL=/downloads/silicium-node-windows.exe
```

Nginx serves this file directly from `/var/lib/silicium/downloads`; rebuilding
or restarting the frontend is not required when only replacing the installer.
Verify the public download after upload:

```bash
curl -I https://YOUR_DOMAIN/downloads/silicium-node-windows.exe
```

## Automatic VPS deployment

`/.github/workflows/deploy-vps.yml` deploys every push to `main` that changes
the site, backend, network, or deployment files. Configure these repository
secrets before enabling it:

- `VPS_HOST`: public VPS hostname or IP;
- `VPS_USER`: SSH deployment user;
- `VPS_SSH_KEY`: private Ed25519 key authorized on the VPS;
- `VPS_KNOWN_HOSTS`: pinned `known_hosts` entry for the VPS;
- `VPS_PORT`: optional SSH port, default `22`;
- `VPS_ROOT`: optional checkout path, default `/opt/silicium`.

The deployment user must be able to run the existing `deploy/linux/build-site.sh`
and the four `systemctl restart` commands through `sudo` without an interactive
password prompt. The workflow performs a fast-forward pull, updates all
submodules, rebuilds the services, publishes the Windows installer, and
restarts the services.

## Remote workers

On a worker machine, install the repo and raytracer runtime, then start:

```bash
bash deploy/linux/start-node.sh worker-1 compute 46101 http://ORCHESTRATOR_PUBLIC_IP:46100 WORKER_PUBLIC_IP demo-mesh 120
```

On a verifier:

```bash
bash deploy/linux/start-node.sh verifier-1 verify 46102 http://ORCHESTRATOR_PUBLIC_IP:46100 VERIFIER_PUBLIC_IP demo-mesh 90
```
