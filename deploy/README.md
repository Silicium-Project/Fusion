# Silicium deployment

This folder contains a first production-oriented VPS deployment for the public
site.

Recommended first public setup:

1. One Linux VPS hosts:
   - Nuxt frontend on `127.0.0.1:3000`
   - Go backend on `127.0.0.1:8080`
   - Devnet dashboard on `127.0.0.1:5174`
   - Silicium orchestrator on public port `46100`
2. Remote worker/verifier machines connect to the VPS orchestrator.
3. Nginx exposes:
   - `https://silicium.example.com`
   - `https://api.silicium.example.com`
   - `https://dashboard.silicium.example.com`

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
sudo certbot --nginx -d silicium.example.com -d api.silicium.example.com -d dashboard.silicium.example.com
```

## Remote workers

On a worker machine, install the repo and raytracer runtime, then start:

```bash
bash deploy/linux/start-node.sh worker-1 compute 46101 http://ORCHESTRATOR_PUBLIC_IP:46100 WORKER_PUBLIC_IP demo-mesh 120
```

On a verifier:

```bash
bash deploy/linux/start-node.sh verifier-1 verify 46102 http://ORCHESTRATOR_PUBLIC_IP:46100 VERIFIER_PUBLIC_IP demo-mesh 90
```
