# Silicium Node

Desktop app for people who want to join the Silicium network as a worker,
verifier, or both.

This app is intentionally separate from:

- `Network/`: core P2P/runtime logic
- `Site/`: public client website
- `deploy/`: VPS deployment assets

The first version is a lightweight Tauri launcher around the existing network
scripts. It does not reimplement the network node.

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

- Windows worker: `Network\scripts\start-worker.cmd`
- Windows verifier: `Network\scripts\start-verifier.cmd`
- Linux/macOS node: `deploy/linux/start-node.sh`

Default public orchestrator:

```text
http://213.32.68.67:46100
```

## Current scope

MVP:

- configure orchestrator URL
- configure advertise host
- choose worker/verifier roles
- start/stop local node processes
- display local process state
- show beta install guidance

Later:

- installer bundled dependencies
- Windows service/background mode
- auto-update
- node identity and wallet onboarding
- reputation and earnings display
