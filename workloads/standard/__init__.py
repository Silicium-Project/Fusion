"""Small, deterministic workloads that run on every Silicium worker."""

from .standard_workloads import run_standard_workload

__all__ = ["run_standard_workload"]
