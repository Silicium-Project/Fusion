"""Orchestrator of a raytracer job on the Silicium network.

The BackEnd starts it through `workloads/raytracer/run_network_job.py`, a thin
compatibility entry point that re-exports the public names below. The tile
pipeline itself (split, milestones, validation, previews, reassembly) runs in
the native `silicium-raytracer` binary via `workloads/raytracer/native.py`.

Module layout (one responsibility each):

- `job`           -- `main()`: ties the steps together, stops the emitter.
- `cli`           -- command-line flags (a BackEnd contract).
- `constants`     -- workload ids, schema names, default Solana program id.
- `job_setup`     -- job directories, worker-role discovery, in-flight limits,
                     local emitter node.
- `job_state`     -- `JobState` shared by the stages; writes the progress JSON.
- `native_steps`  -- `make_split` / `reassemble_fragments` (native binary).
- `pipeline`      -- bounded compute/verify scheduler, `RetryFragmentStage`.
- `compute_stage` -- dispatch a tile, check its result, store tile and preview.
- `verify_stage`  -- challenge one milestone, check the attestation.
- `stage_common`  -- submission, attempt polling and result bookkeeping shared
                     by both stages.
- `retries`       -- retry policy for transient failures, peer exclusion.
- `polling`       -- result / dead-letter files, queue and execution deadlines.
- `peers`         -- worker capacity from the emitter's peer snapshot.
- `dispatch`      -- submission to the scheduler (local queue, RPC, HTTP).
- `content_refs`  -- content references (mesh store or local files).
- `failures`      -- failed-result details, transient classification,
                     compute result contract.
- `receipts`      -- signed compute receipt and verifier attestation checks.
- `performance`   -- per-task records and job performance summary.
- `summary`       -- reassembly, billing, summary JSON, exit code.
- `devnet`        -- optional Solana devnet trace.

Files written for the BackEnd are described in docs/contracts/backend-files.md.
"""
