# Silicium Node

Desktop app for people who want to join the Silicium network with their PC.
Windows is the production channel; Linux AppImage/deb/rpm builds are available
on the development channel.

This app is intentionally separate from:

- `Network/`: core P2P/runtime logic
- `Site/`: public client website
- `deploy/`: VPS deployment assets

The app is a Tauri shell around the Silicium network node, the Rust
`p2p_node` binary (with `compute_daemon` and the native raytracer). It does not
reimplement the node. The installer bundles these binaries so a normal user
can install the app, click one button, and join the network with `compute,verify`
capabilities. The network/orchestrator decides what work is assigned over time.

The installed application keeps its managed runtime, node identity, logs and
task history under `%APPDATA%\SiliciumNode`. Closing the window does not stop
the activated worker: the application remains available from the Windows
notification area. Its menu can start, stop or restart the managed service,
open the dashboard, or quit the desktop shell without stopping the worker.
The notification-area shell and supervisor are restored when the Windows
session starts.

## Rust backend layout (`src-tauri/src/`)

| Module | Role |
| --- | --- |
| `main.rs` | Entry point: desktop app, `--supervisor` or `--cleanup` |
| `lib.rs` | Shared imports, module list, `run()` (Tauri builder, command registration) |
| `commands.rs` | Tauri commands called by the frontend |
| `types.rs` | Data types sent to the frontend and persisted on disk |
| `config.rs` | Constants, node id, orchestrator URL, service configuration file |
| `runtime.rs` | Repository root, managed / packaged runtime, child process environment |
| `node.rs` | Starting the node process and waiting for it to be ready |
| `supervisor.rs` | Supervisor mode (restart on stale claim poll) |
| `process.rs` | Stopping nodes, `--cleanup`, process trees |
| `service.rs` | Windows service / Run key and Linux autostart |
| `paths.rs` | PID files and application state directory |
| `checks.rs` | Environment checks shown in the UI |
| `ai.rs` | AI tasks (opt-in): downloads the pinned Ollama release (hash checked), runs it on `127.0.0.1:11435` next to the node, stops it with the node |
| `activity/` | Logs, task history, per-machine activity (`machine.rs`) |
| `update/` | Self-update: status and locks (`mod.rs`), manifest and signature (`manifest.rs`), download and install (`install.rs`) |
| `http.rs`, `logging.rs` | `curl` helpers, hashing, app error log |
| `tray.rs` | Windows notification-area menu |
| `tests.rs` | Unit tests |

Every module starts with `use crate::*;`: `lib.rs` holds the shared imports and
glob-imports each module, so items only need `pub(crate)` to be visible across
modules.

## Development

Requirements:

- Node.js 20+
- Rust stable
- Tauri prerequisites for your OS

From this folder on Windows:

```bash
npm install
npm run tauri:dev
```

On Linux, install the Tauri 2 WebKitGTK prerequisites, then run:

```bash
npm ci
npm run prepare:runtime:linux
npm run tauri:dev
```

## Build

```bash
npm run tauri:build
```

Linux development bundles:

```bash
npm run tauri:build:linux
```

This produces `silicium-node-*.AppImage`, `silicium-node-*.deb` and
`silicium-node-*.rpm`. The `.deb` and `.rpm` outputs are published into signed
APT and DNF repositories on the VPS. Install from the repository so the
package manager selects and fetches the package; no manual local installer
file is needed. Production and development repository setup commands are in
[`deploy/README.md`](../../deploy/README.md).

The AppImage remains the portable option when its host dependencies are
already present.

The AppImage keeps the same bundled Network runtime and can be used without
installation on a distribution that already provides OpenSSL, curl,
certificates and the Tauri WebKit runtime. After downloading it, make it
executable once before launching it:

```bash
chmod +x silicium-node-*.AppImage
./silicium-node-*.AppImage
```

Activation installs an XDG autostart entry under `~/.config/autostart`. When
started from an AppImage, that entry points to the downloaded AppImage file,
not to its temporary mounted directory.

Before Tauri bundles the installer, `npm run prepare:runtime` (Windows) or
`npm run prepare:runtime:linux` stages a runtime under
`src-tauri/resources/runtime` containing:

- `Network/bin/p2p_node` and `Network/bin/compute_daemon`, built from
  `Network/` with Cargo
- the native raytracer in `Network/bin/raytracer/`
- `.silicium/env/raytracer.env`, which points the compute daemon at it

No Python and no OpenSSL are bundled. On start, the app removes from the
managed runtime the files of older bundles that shipped the former Python node
(`remove_legacy_runtime_assets`).

The staged runtime is generated and ignored by Git. Rebuild it with:

```bash
npm run prepare:runtime
```

Default public orchestrator:

```text
https://vps-910c1dbc.vps.ovh.net/orchestrator
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
