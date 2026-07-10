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

4. Publish it either:

- in a GitHub Release and set `NUXT_PUBLIC_NODE_APP_WINDOWS_URL` to the release asset URL;
- or on the VPS under the persistent downloads path.

For local site testing, copy the installer to:

```text
/var/lib/silicium/downloads/silicium-node-windows.exe
```

Do not commit generated installers to the repository unless the team explicitly
decides to version release binaries.
