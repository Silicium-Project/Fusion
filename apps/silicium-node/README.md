# Silicium Node

Desktop app for people who want to join the Silicium network with their PC.

This app is intentionally separate from:

- `Network/`: core P2P/runtime logic
- `Site/`: public client website
- `deploy/`: VPS deployment assets

The app is a Tauri shell around the existing Silicium network node. It does not
reimplement the node. The installer bundles a minimal runtime so a normal user
can install the app, click one button, and join the network with `compute,verify`
capabilities. The network/orchestrator decides what work is assigned over time.

The installed application keeps its managed runtime, node identity, logs and
task history under `%APPDATA%\SiliciumNode`. Closing the window does not stop
the activated worker: its supervisor continues in the background and is
restored when the Windows session starts.

## Development

Requirements:

- Node.js 20+
- Rust stable
- Tauri prerequisites for your OS

From this folder:

```bash
npm install
npm run tauri:dev
```

## Build

```bash
npm run tauri:build
```

Before Tauri bundles the installer, `npm run prepare:runtime` stages a runtime
under `src-tauri/resources/runtime` containing:

- the minimal `Network/` runtime needed by the node
- the raytracer executable and DLLs from `Network/bin/raytracer`
- Python copied from `apps/silicium-node/vendor/python` when present, otherwise
  from the local Windows Python install
- OpenSSL copied from `apps/silicium-node/vendor/openssl` when present, otherwise
  from the local Windows OpenSSL install

The staged runtime is generated and ignored by Git. Rebuild it with:

```bash
npm run prepare:runtime
```

Default public orchestrator:

```text
http://213.32.68.67:46100
```

## Current scope

MVP:

- one-click activation for non-technical users
- automatic repo/IP/default configuration detection
- bundled runtime for installed users
- start/stop one local node with compute and verify roles
- display local process state, activity, history, and diagnostics
- display connected machines, active fragments/verifications, and last response status
- preserve identity and history across repair installs and upgrades
- log native startup failures to `%APPDATA%\SiliciumNode\silicium-app.err.log`

Task lifecycle details are persisted in `node.events.ndjson`. Heartbeats and
peer announcements expose the active task, role, fragment index, input source,
processing result, and whether a dispatched result reached its origin node.

Later:

- Windows service/background mode
- auto-update
- node identity and wallet onboarding
- reputation and earnings display
- live task assignment and resource metrics
