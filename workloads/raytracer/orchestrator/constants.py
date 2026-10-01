"""Constants shared by the raytracer job orchestrator modules.

Workload identifiers, schema names and defaults live here so that every
module (and the BackEnd contract in docs/contracts/backend-files.md) refers
to a single definition.
"""
from __future__ import annotations

from pathlib import Path

# Repository root (the `Network` folder): workloads/raytracer/orchestrator/ -> Network/.
NETWORK_ROOT = Path(__file__).resolve().parents[3]

RAYTRACER_FRAGMENT_COMPUTE_WORKLOAD = "calcul/rendering/raytracer-fragment"
RAYTRACER_FRAGMENT_VERIFY_WORKLOAD = "verification/rendering/raytracer-fragment"
RAYTRACER_PERFORMANCE_SCHEMA = "silicium.raytracer-performance.v1"

# Feature flag a worker must advertise to receive raytracer tiles. Legacy
# workers whose renderer progress writes serialize the pixel loop lack it.
RAYTRACER_FASTPATH_FEATURE = "raytracer_fastpath_v1"

# Canonical Silicium program id on Solana; overridable with
# SILICIUM_SOLANA_PROGRAM_ID or --solana-program-id.
DEFAULT_SOLANA_PROGRAM_ID = "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"
