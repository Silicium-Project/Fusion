# Raytracer workload

This folder adapts an externally installed raytracer executable to the Silicium
workload contract. The repository contains the network adapter, not the
raytracer source project.

Entrypoints:

```powershell
py Network\workloads\raytracer\split.py Network\workloads\raytracer\examples\demo-scene.cfg --output .silicium\raytracer-split.json
py Network\workloads\raytracer\compute.py --scene Network\workloads\raytracer\examples\demo-scene.cfg --output .silicium\fragment-0.ppm --y-start 0 --y-end 120
py Network\workloads\raytracer\verify.py --scene Network\workloads\raytracer\examples\demo-scene.cfg --result .silicium\fragment-0.ppm --expected-hash sha256:<hash> --y-start 0 --y-end 120
py Network\workloads\raytracer\reassemble.py --fragment .silicium\fragment-0.ppm --y-start 0 --fragment .silicium\fragment-1.ppm --y-start 120 --output .silicium\raytracer-final.ppm --png .silicium\raytracer-final.png
```

The split policy is automatic horizontal bands. The site only sends
`workload=raytracer` and a `.cfg`; the orchestrator estimates the fragment count
from the scene resolution, distributes fragments to workers, verifies them, then
reassembles the final image.

Runtime requirements:

- Set `SILICIUM_RAYTRACER_BIN` to the absolute path of the raytracer executable
  on every compute and verify worker.
- Make the raytracer runtime libraries available on the worker PATH or beside
  the executable.
- If scenes reference external assets, set `SILICIUM_RAYTRACER_ASSETS_DIR` to
  the folder containing those assets. If omitted, the adapter tries an `assets`
  folder next to the executable.
