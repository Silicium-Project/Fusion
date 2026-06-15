# Render3D workload

This folder contains the reusable Render3D workload implementation. Demo scripts may orchestrate jobs, Devnet tracing, and local files, but worker/verifier execution should enter through this workload.

## Entrypoints

```powershell
py Network\workloads\render3d\split.py Network\demo\render3d\scene.json --output .silicium\split.json
py Network\workloads\render3d\compute.py --scene Network\demo\render3d\scene.json --output .silicium\fragment.ppm --y-start 0 --y-end 100
py Network\workloads\render3d\verify.py --scene Network\demo\render3d\scene.json --result .silicium\fragment.ppm --expected-hash sha256:<hash> --y-start 0 --y-end 100
py Network\workloads\render3d\reassemble.py --fragment .silicium\fragment-0.ppm --fragment .silicium\fragment-1.ppm --output .silicium\render.ppm --png .silicium\render.png
```

## Contract

- `split` produces fragment specs and a recursive split tree.
- `compute` renders either the full scene or one horizontal fragment.
- `verify` recomputes deterministically and compares hashes.
- `reassemble` joins verified horizontal fragments into the final render.

The network core should depend on this contract, not on the demo folder.
