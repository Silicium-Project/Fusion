# Silicium site integration

This folder contains the client-facing site and backend API, both tracked as Git submodules.

Responsibilities stay separated:

- `FrontEnd`: user dashboard, task submission form, result display link, and
  link to the read-only Devnet dashboard.
- `BackEnd`: authenticated API, job persistence, file upload, and bridge to the
  Silicium network runner.
- `../Network`: P2P nodes, workers/verifiers, render workload, reassembly, and
  Devnet trace/dashboard.

## First integrated flow

1. Start worker/verifier nodes from `Network/`.
2. Start the Devnet dashboard from `Network/`.
3. Start the backend with Silicium bridge environment variables.
4. Start the Nuxt frontend.
5. Submit a `scene.json` file from the user dashboard.
6. The backend creates a `jobs` row, runs the Silicium network demo, updates the
   job status, and exposes the final render through `GET /jobs/{id}/result`.

## Backend environment

```shell
DATABASE_URL=host=localhost user=... password=... dbname=... port=5432 sslmode=disable
JWT_SECRET_KEY=change-me
SILICIUM_NETWORK_ROOT=../../Network
SILICIUM_SEED_PEERS=http://127.0.0.1:46101,http://127.0.0.1:46102
SILICIUM_MESH_KEY=demo-mesh
SILICIUM_ORCHESTRATOR_HOST=127.0.0.1
SILICIUM_DASHBOARD_URL=http://localhost:5174/
SILICIUM_DEVNET_TRACE=1
SILICIUM_DEVNET_TX_DELAY_MS=2500
```

## Frontend environment

```shell
NUXT_PUBLIC_API_BASE=http://localhost:8080
NUXT_PUBLIC_DEVNET_DASHBOARD_URL=http://localhost:5174/
```
