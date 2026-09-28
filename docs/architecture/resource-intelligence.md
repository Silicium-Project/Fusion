# Resource intelligence

Silicium nodes publish two backward-compatible, versioned objects in their
heartbeat, peer announcements, discovery registration, and peer directory.

## Resource profile

`capacity.resource_profile` uses schema `silicium.resource-profile.v1`. It
contains portable CPU, memory, storage, platform, and runtime-observed network
fields. GPU, battery, and thermal fields remain explicit with
`status: not_probed` until a platform adapter can measure them safely.

The benchmark protocol `silicium.resource-benchmark.v1` measures SHA-256
compute and verification throughput and a verified 256 KiB disk sample. The
work is bounded to a few tens of milliseconds and cached for five minutes, so
heartbeat generation cannot become a meaningful worker workload.

## Per-resource reputation

`resource_reputation` uses schema `silicium.resource-reputation.v1` and keeps
independent Beta distributions for:

- `connection`
- `storage`
- `compute`
- `verify`
- `delegation`

Each distribution has a five-minute short-term half-life and a 30-day
long-term half-life. Transient failures mainly affect short-term memory;
verified outcomes feed both; integrity violations have four times their base
weight in long-term memory.

Compute, verification, storage, and delegation benchmarks seed only two units
of synthetic evidence per memory. Their prior mean is deliberately constrained
between one third and two thirds: hardware can establish expected capability,
but it cannot manufacture trust. Observed network outcomes then dominate it.

The snapshot exposes the posterior mean, approximate 95% lower and upper
confidence bounds, and evidence count. Scheduling uses the lower confidence
bound for the requested role, mixed with the connection bound, while retaining
the legacy scalar reputation as a fallback for older peers.

The persisted `node.<id>.reputation.json` remains readable by old code and now
uses `schema_version: 2`. Existing `local_score`, `peer_scores`, and `history`
fields are unchanged.
