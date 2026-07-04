# Silicium Node

Desktop app for people who want to join the Silicium network with their PC.

This app is intentionally separate from:

- `Network/`: core P2P/runtime logic
- `Site/`: public client website
- `deploy/`: VPS deployment assets

The first version is a lightweight Tauri launcher around the existing network
scripts. It does not reimplement the network node. The app starts one local node
with `compute,verify` capabilities; the network/orchestrator decides what work
is assigned over time.

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

The app asks for the local repository path so it can call the existing scripts:

- Windows node: `Network\demo\networked\start-node.cmd`
- Linux/macOS node: `deploy/linux/start-node.sh`

Default public orchestrator:

```text
http://213.32.68.67:46100
```

## Current scope

MVP:

- install/repair runtime from the existing repo installer
- run system checks
- configure orchestrator URL
- configure advertise host
- start/stop one local node with compute and verify roles
- display local process state
- show local activity and recent files

Later:

- standalone installer with bundled runtime
- Windows service/background mode
- auto-update
- node identity and wallet onboarding
- reputation and earnings display
- live task assignment and resource metrics
