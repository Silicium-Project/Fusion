# Publish Silicium Node

The public site already points to:

```text
/downloads/silicium-node-windows.exe
```

Recommended production flow:

1. Build the desktop app on a Windows machine:

```powershell
cd apps\silicium-node
npm.cmd install
npm.cmd run tauri:build
```

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
