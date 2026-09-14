# Publish Silicium Node

The public site exposes these VPS download paths:

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

The AppImage, Debian package and RPM are built from the same Linux release and
contain the same Network runtime. Use the AppImage for a portable test run;
use the `.deb` on Debian/Ubuntu with `apt`, or the `.rpm` on Fedora/RHEL with
`dnf`, so host dependencies are installed by the native package manager. The
Linux client resolves Tauri's `/usr/lib/<binary>/resources` layout in all three
formats.

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
the GitHub Release and stage them under the persistent VPS downloads path. The
public site uses the VPS paths above, so the web links and the updater use the
same files.

Production package repositories are generated beside the direct downloads. The
APT repository is signed with the channel key published at
`/downloads/apt/silicium-packages.asc`; the DNF repository definition is at
`/downloads/rpm/silicium-node.repo`. The dev repository uses the private
WireGuard URL and the suite `dev`.

For local site testing, copy the installer to:

```text
/var/lib/silicium/downloads/silicium-node-windows.exe
```

Do not commit generated installers to the repository unless the team explicitly
decides to version release binaries.
