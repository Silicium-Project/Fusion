# Raytracer workload

This folder contains the Python orchestration of the raytracer workload. The
native renderer lives in `crates/raytracer/`: a deterministic Rust engine with recursive reflections, shadows,
Phong highlights and row-parallel CPU execution. The desktop packaging scripts
build it for the target platform. `SILICIUM_RAYTRACER_THREADS` or `--threads`
can cap its worker count; otherwise it uses the logical CPU count.

The whole tile pipeline runs in the native binary (see
`crates/raytracer/README.md`): scene size, splitting, milestone commitments,
probabilistic verification, fragment validation, PNG previews and reassembly.
The Python code here only orchestrates it and calls the binary through
`native.py` (`SILICIUM_PIPELINE_BIN` on the orchestrator, else
`SILICIUM_RAYTRACER_BIN`). There is no Python PPM parser or milestone code.

| File | Role |
| --- | --- |
| `native.py` | Calls the `silicium-raytracer` pipeline sub-commands |
| `run_network_job.py` | Orchestrator: split, dispatch, verify, reassemble a job |
| `node_tasks.py` | Node handlers: compute a tile, verify a challenged milestone |
| `raytracer_workload.py` (+ `compute.py`, `verify.py`) | Render / verify / validate one tile from the command line |

Entrypoints:

```powershell
silicium-raytracer split Network\workloads\raytracer\examples\demo-scene.cfg --output .silicium\raytracer-split.json
py Network\workloads\raytracer\compute.py --scene Network\workloads\raytracer\examples\demo-scene.cfg --output .silicium\fragment-0.ppm --y-start 0 --y-end 120
py Network\workloads\raytracer\verify.py --scene Network\workloads\raytracer\examples\demo-scene.cfg --result .silicium\fragment-0.ppm --expected-hash sha256:<hash> --y-start 0 --y-end 120
silicium-raytracer reassemble --fragment .silicium\fragment-0.ppm --y-start 0 --fragment .silicium\fragment-1.ppm --y-start 120 --output .silicium\raytracer-final.ppm --png .silicium\raytracer-final.png
```

The split policy uses rectangular center-out neighbour tiles. Each compute
worker commits the pixel hashes of smaller row milestones (20 rows by default).
After the complete
fragment has been returned, the orchestrator randomly selects one milestone and
sends only that challenge plus the scene to a different verifier. The verifier
re-renders the challenged rows instead of the complete fragment. Configure the
batch size with `SILICIUM_RAYTRACER_VERIFY_BATCH_ROWS` or
`--verification-batch-rows`.

The site only sends `workload=raytracer` and a `.cfg`; the emitter estimates the
fragment count from the scene resolution, distributes fragments to workers,
challenges one milestone per fragment, then reassembles the final image.

Runtime requirements:

- The desktop runtime configures `SILICIUM_RAYTRACER_BIN` to its bundled native
  executable. Set it manually only for source/development installations.
- Make the raytracer runtime libraries available on the worker PATH or beside
  the executable.
- If scenes reference external assets, set `SILICIUM_RAYTRACER_ASSETS_DIR` to
  the folder containing those assets. If omitted, the adapter tries an `assets`
  folder next to the executable.
