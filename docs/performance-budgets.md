# Performance and resource budgets

`docs/performance-budgets.json` contains guardrails for the active Network
runtime. It intentionally does not contain profiles for the removed C++
fragment pipeline.

Metrics are elapsed time (`wall_sec`), CPU time (`cpu_sec`), and peak resident
memory (`max_rss_kib`). Profiles can restrict supported platforms and can be
run individually or together:

```bash
python3 tools/perf_budget.py --list
./silicium budget --all --strict --output /tmp/network-budget.json
./silicium budget --profile network_check --strict
```

Run default profile:

```bash
./silicium budget
```

Run all profiles with strict thresholds:

```bash
./silicium budget --all --strict --output /tmp/perf-budget-report.json
```

Run a platform-specific profile:

```bash
./silicium budget --profile pytest_core_windows --strict
```

## CI Usage

Workflow `ci.yml` runs budget checks through the canonical Network CI entry
point, using the reusable lane workflows underneath.
