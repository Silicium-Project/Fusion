# Publish Silicium Node

The release workflow stages these artifacts under the VPS downloads path:

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

The `.deb` and `.rpm` outputs are published inside signed APT and DNF
repositories. Install the package named `silicium-node` through the system
package manager; setup commands for both channels are in
[`deploy/README.md`](../../deploy/README.md), so there is no need to download a
local installer file. The direct artifact paths remain available for
compatibility. The AppImage remains available for portable testing. All three
formats contain the same Network runtime, and the Linux client resolves
Tauri's `/usr/lib/<binary>/resources` layout in each format.

Recommended production flow:

The updater uses two independent channels published in
`/downloads/update-manifest.json`:

- `dev`: SemVer prereleases such as `0.2.9-dev.20`, checked every 30 seconds;
- `prod`: stable SemVer releases such as `0.2.17`, checked every 6 hours.

The legacy `channels` map remains available for the website, while the signed
`releases` list contains one entry per platform. Linux clients select the
`linux-x86_64` AppImage entry and never attempt to install the Windows `.exe`.

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

4. The Fusion `Deploy` workflow signs both the application and the installer
   with the organization Windows code-signing certificate before publishing.
   Configure these repository Actions secrets before pushing a node release:

   - `SILICIUM_WINDOWS_CERTIFICATE_BASE64`: the base64-encoded PFX containing
     the code-signing certificate and private key;
   - `SILICIUM_WINDOWS_CERTIFICATE_PASSWORD`: the PFX password.

   The private certificate must never be committed to Git. An unsigned build
   is suitable for local development only: SmartScreen or endpoint protection
   may quarantine it, which leaves Windows shortcuts pointing to a missing
   file.

   For test-only packaging, the workflow can use a self-signed PFX when the
   repository variable `SILICIUM_WINDOWS_ALLOW_SELF_SIGNED` is set to `true`.
   This only makes the runner trust the test certificate; Windows users will
   still see it as untrusted.

Verify the release artifact before upload:

```powershell
Get-AuthenticodeSignature .\silicium-node-windows.exe
```

The status must be `Valid`. Keep the Tauri identifier
`network.silicium.node` stable and increment the application version for every
published installer so NSIS can repair or upgrade an existing installation.

5. Let the Fusion deployment workflow publish the generated artifacts to
the GitHub Release and stage the Linux packages under the persistent VPS
downloads path. The package repository publisher adds the current package to
the signed APT and DNF indexes. The updater continues to use the Windows and
AppImage artifacts.

Production and development repositories are generated on each deployment.
APT metadata is signed with the channel key published at
`/downloads/apt/silicium-packages.asc`. RPM packages and DNF metadata are signed
with the channel key published at
`/downloads/rpm/silicium-rpm-signing.asc`; the DNF repository definition is at
`/downloads/rpm/silicium-node.repo`. The dev repository uses the private
WireGuard URL and the APT suite `dev`.

For local site testing, copy the installer to:

```text
/var/lib/silicium/downloads/silicium-node-windows.exe
```

Do not commit generated installers to the repository unless the team explicitly
decides to version release binaries.
