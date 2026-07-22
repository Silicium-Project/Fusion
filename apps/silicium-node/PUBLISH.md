# Publish Silicium Node

The public site already points to:

```text
/downloads/silicium-node-windows.exe
```

Recommended production flow:

The updater uses two independent channels published in
`/downloads/update-manifest.json`:

- `dev`: SemVer prereleases such as `0.2.9-dev.12`, checked every 30 seconds;
- `prod`: stable SemVer releases such as `0.2.17`, checked every 6 hours.

Builds must set `SILICIUM_RELEASE_CHANNEL`, `SILICIUM_RELEASE_VERSION`, and
`SILICIUM_RELEASE_BUILD`. The supervisor reports those exact compiled values in
the P2P heartbeat and installs a newer version or a different published build
silently when the node is idle. The server-side
`silicium-update-manifest.timer` refreshes build IDs, hashes, sizes, and URLs
every 30 seconds during development.

1. Build the desktop app on a Windows machine:

```powershell
cd apps\silicium-node
npm.cmd install
npm.cmd run tauri:build
```

For a stable installer, set `SILICIUM_RELEASE_CHANNEL=prod` and run
`build-installer.cmd`. It merges `tauri.prod.conf.json`, so both the NSIS
installer and the compiled heartbeat telemetry report the stable version.

2. Find the generated Windows installer in:

```text
apps\silicium-node\src-tauri\target\release\bundle\
```

3. Rename/copy the installer to:

```text
silicium-node-windows.exe
```

4. Sign both the application and the installer with the organization Windows
   code-signing certificate before publishing. An unsigned build is suitable
   for local development only: SmartScreen or endpoint protection may
   quarantine it, which leaves Windows shortcuts pointing to a missing file.

Verify the release artifact before upload:

```powershell
Get-AuthenticodeSignature .\silicium-node-windows.exe
```

The status must be `Valid`. Keep the Tauri identifier
`network.silicium.node` stable and increment the application version for every
published installer so NSIS can repair or upgrade an existing installation.

5. Publish it either:

- in a GitHub Release and set `NUXT_PUBLIC_NODE_APP_WINDOWS_URL` to the release asset URL;
- or on the VPS under the persistent downloads path.

For local site testing, copy the installer to:

```text
/var/lib/silicium/downloads/silicium-node-windows.exe
```

Do not commit generated installers to the repository unless the team explicitly
decides to version release binaries.
