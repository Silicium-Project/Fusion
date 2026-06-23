# Raytracer runtime binary

Place the packaged raytracer executable for worker machines here:

```text
Network/bin/raytracer/raytracer.exe
```

`install-silicium-windows.cmd` detects this path automatically and writes the
local runtime configuration to `.silicium/env/raytracer.env`.

The source project is intentionally not stored in this repository. Workers only
need the executable and its runtime DLLs/libraries.
