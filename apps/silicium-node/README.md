# Silicium Node

Desktop app for people who want to join the Silicium network with their PC.
Windows is the production channel; Linux AppImage/deb/rpm builds are available
on the development channel.

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
the activated worker: the application remains available from the Windows
notification area. Its menu can start, stop or restart the managed service,
open the dashboard, or quit the desktop shell without stopping the worker.
The notification-area shell and supervisor are restored when the Windows
session starts.

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
`silicium-node-*.rpm`. The Debian package is the recommended Linux install on
Debian/Ubuntu because it declares the Python, OpenSSL, curl and certificate
dependencies:

```bash
sudo apt install ./silicium-node-*.deb
```

On Fedora/RHEL, install the RPM with the native package manager:

```bash
sudo dnf install ./silicium-node-*.rpm
```

The published `.deb` and `.rpm` files are also directly installable from the
site after downloading them. The package managers resolve their declared
dependencies; the AppImage remains the portable option when those host
dependencies are already present.

The AppImage keeps the same bundled Network runtime and can be used without
installation on a distribution that already provides Python 3, OpenSSL, curl,
certificates and the Tauri WebKit runtime. After downloading it, make it
executable once before launching it:

```bash
chmod +x silicium-node-*.AppImage
./silicium-node-*.AppImage
```

Activation installs an XDG autostart entry under `~/.config/autostart`. When
started from an AppImage, that entry points to the downloaded AppImage file,
not to its temporary mounted directory.

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
