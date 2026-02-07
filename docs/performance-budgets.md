# Performance and Energy Budgets

Issue reference: `#120`

This document defines versioned guardrails for command runtime and host pressure.

Budget file: `docs/performance-budgets.json`

## Metrics

- `wall_sec`: total elapsed time in seconds.
- `cpu_sec`: user + system CPU seconds (energy proxy).
- `max_rss_kib`: peak resident memory in KiB.

## Profiles

- `check_worker_quick`: quick worker-focused core check.
- `pytest_core`: core Python tests subset.
- `splitter_demo`: representative splitter/executor run.

## Local Usage

List profiles:

```bash
python3 tools/perf_budget.py --list
```

Run default profile:

```bash
./silicium budget
```

Run all profiles with strict thresholds:

```bash
./silicium budget --all --strict --output /tmp/perf-budget-report.json
```

## CI Usage

Workflow `tests.yml` runs budget checks with `--all --strict`, uploads JSON metrics,
and prints a summary to the job report.
