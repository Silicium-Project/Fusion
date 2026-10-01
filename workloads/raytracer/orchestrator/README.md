# Raytracer job orchestrator

Runs one raytracer job on the network: split the scene, dispatch a compute
task per fragment, challenge one milestone of each fragment on another worker,
check the signed receipts, reassemble the image and write the files the
BackEnd reads (`docs/contracts/backend-files.md`).

The BackEnd and the workload manifest start it through
`workloads/raytracer/run_network_job.py`, which only bootstraps `sys.path`
and re-exports the public names of this package. The tile pipeline itself
runs in the native `silicium-raytracer` binary (`../native.py`).

| Module | Role |
| --- | --- |
| `job.py` | `main()`: runs the steps in order, always stops the emitter |
| `cli.py` | Command-line flags and their environment defaults |
| `constants.py` | Workload ids, schema names, default Solana program id |
| `job_setup.py` | Job directories, worker-role discovery, in-flight limits, emitter node |
| `job_state.py` | `JobState` shared by the stages; writes `raytracer-progress.json` |
| `native_steps.py` | `make_split` / `reassemble_fragments` through the native binary |
| `pipeline.py` | Bounded compute/verify scheduler (`run_bounded_fragment_pipeline`) |
| `compute_stage.py` | Compute dispatch, result checks, tile and preview storage |
| `verify_stage.py` | Milestone challenge, verify dispatch, attestation checks |
| `stage_common.py` | Submission, attempt polling and result bookkeeping shared by both stages |
| `retries.py` | Retry policy for transient failures, peer exclusion |
| `polling.py` | Result and dead-letter files, queue/execution deadlines |
| `peers.py` | Worker capacity from the emitter's peer snapshot |
| `dispatch.py` | Submission to the scheduler (local queue, RPC sidecar, signed HTTP) |
| `content_refs.py` | Content references (mesh content store or local files) |
| `failures.py` | Failed-result details, transient classification, compute contract |
| `receipts.py` | Signed compute receipt and verifier attestation checks |
| `performance.py` | Per-task performance records and job summary |
| `summary.py` | Reassembly, billing, `raytracer-summary.json`, exit code |
| `devnet.py` | Optional Solana devnet trace (`--devnet-trace`) |

Flow: `job.main` -> `job_setup` -> `native_steps.make_split` ->
`pipeline.run_bounded_fragment_pipeline` (`compute_stage` then `verify_stage`
per fragment, retries through `retries`) -> `summary.finalize_job`.
