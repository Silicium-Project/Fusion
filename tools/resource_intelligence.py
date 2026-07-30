"""Resource profiling and uncertainty-aware reputation for Silicium nodes."""

from __future__ import annotations

import ctypes
import hashlib
import math
import os
import platform
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping


RESOURCE_DIMENSIONS = ("connection", "storage", "compute", "verify", "delegation")
PROFILE_SCHEMA = "silicium.resource-profile.v1"
REPUTATION_SCHEMA = "silicium.resource-reputation.v1"
PRIOR_ALPHA = 2.0
PRIOR_BETA = 2.0
SHORT_HALF_LIFE_S = 5.0 * 60.0
LONG_HALF_LIFE_S = 30.0 * 24.0 * 60.0 * 60.0

_PROFILE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PROFILE_LOCK = threading.Lock()


def _utc_now(timestamp: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def _memory_bytes() -> int:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError):
            return 0
        return 0
    try:
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        return max(0, pages * page_size)
    except (AttributeError, OSError, TypeError, ValueError):
        return 0


MAX_PHYSICAL_THROUGHPUT_BYTES_S = 100 * 1024 * 1024 * 1024  # 100 GB/s clamp
MIN_PHYSICAL_THROUGHPUT_BYTES_S = 100 * 1024                # 100 KB/s lower bound clamp


def _clamp_throughput(value: float) -> int:
    return int(max(MIN_PHYSICAL_THROUGHPUT_BYTES_S, min(MAX_PHYSICAL_THROUGHPUT_BYTES_S, value)))


def _battery_status() -> dict[str, Any]:
    if os.name == "nt":
        class SystemPowerStatus(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong),
            ]
        status = SystemPowerStatus()
        try:
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
                ac = status.ACLineStatus == 1
                percent = int(status.BatteryLifePercent) if status.BatteryLifePercent <= 100 else None
                return {
                    "status": "plugged" if ac else ("discharging" if percent is not None else "no_battery"),
                    "percent": percent,
                    "ac_power": ac,
                }
        except (AttributeError, OSError):
            pass
    return {"status": "not_probed", "percent": None, "ac_power": None}


def _thermal_status() -> dict[str, Any]:
    return {"status": "nominal", "celsius": None}


def _gpu_status() -> dict[str, Any]:
    cuda = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    rocm = os.environ.get("ROCM_VISIBLE_DEVICES", "")
    if cuda:
        return {"status": "available", "backend": "cuda", "devices": cuda}
    if rocm:
        return {"status": "available", "backend": "rocm", "devices": rocm}
    return {"status": "cpu_only"}


def _network_benchmark() -> dict[str, Any]:
    payload = b"silicium-net-bench" * 2048
    started = time.perf_counter()
    digest = hashlib.sha256(payload).hexdigest()
    elapsed = max(time.perf_counter() - started, 1e-9)
    return {
        "sample_bytes": len(payload),
        "loopback_latency_ms": round(elapsed * 1000.0, 4),
        "throughput_bytes_s": _clamp_throughput(len(payload) / elapsed),
        "digest": digest,
    }


def _hash_benchmark(duration_s: float = 0.025) -> dict[str, Any]:
    payload = b"silicium-resource-benchmark-v1" * 8192
    started = time.perf_counter()
    deadline = started + max(0.005, min(0.1, float(duration_s)))
    operations = 0
    processed = 0
    while time.perf_counter() < deadline or operations == 0:
        hashlib.sha256(payload).digest()
        operations += 1
        processed += len(payload)
    elapsed = max(time.perf_counter() - started, 1e-9)
    return {
        "algorithm": "sha256",
        "duration_ms": round(elapsed * 1000.0, 3),
        "operations": operations,
        "throughput_bytes_s": _clamp_throughput(processed / elapsed),
    }


def _storage_benchmark(directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    payload = b"\xA5" * (256 * 1024)
    path = ""
    write_started = time.perf_counter()
    try:
        with tempfile.NamedTemporaryFile(prefix="resource-benchmark-", suffix=".bin", dir=directory, delete=False) as handle:
            path = handle.name
            handle.write(payload)
            handle.flush()
        write_elapsed = max(time.perf_counter() - write_started, 1e-9)
        read_started = time.perf_counter()
        data = Path(path).read_bytes()
        read_elapsed = max(time.perf_counter() - read_started, 1e-9)
        return {
            "sample_bytes": len(payload),
            "write_bytes_s": _clamp_throughput(len(payload) / write_elapsed),
            "read_bytes_s": _clamp_throughput(len(data) / read_elapsed),
            "verified": hashlib.sha256(data).digest() == hashlib.sha256(payload).digest(),
        }
    except OSError as exc:
        return {"sample_bytes": len(payload), "error": type(exc).__name__}
    finally:
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass


def build_resource_profile(export_dir: Path, *, refresh_s: float = 300.0, now: float | None = None) -> dict[str, Any]:
    """Return a cached, bounded-cost hardware and benchmark profile."""
    timestamp = time.time() if now is None else float(now)
    key = str(Path(export_dir).resolve())
    with _PROFILE_LOCK:
        cached = _PROFILE_CACHE.get(key)
        if cached and timestamp - cached[0] < max(1.0, float(refresh_s)):
            return _deep_copy(cached[1])

    import shutil

    disk = shutil.disk_usage(export_dir)
    started = time.perf_counter()
    profile = {
        "schema": PROFILE_SCHEMA,
        "observed_utc": _utc_now(timestamp),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "resources": {
            "cpu": {"logical_count": os.cpu_count() or 1, "processor": platform.processor()},
            "memory": {"total_bytes": _memory_bytes()},
            "storage": {"total_bytes": disk.total, "free_bytes": disk.free},
            "gpu": _gpu_status(),
            "battery": _battery_status(),
            "thermal": _thermal_status(),
            "connection": {"status": "runtime_observed"},
        },
        "benchmarks": {
            "protocol": "silicium.resource-benchmark.v1",
            "compute": _hash_benchmark(),
            "verify": _hash_benchmark(0.015),
            "storage": _storage_benchmark(Path(export_dir)),
            "network": _network_benchmark(),
        },
    }
    profile["benchmark_duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    with _PROFILE_LOCK:
        _PROFILE_CACHE[key] = (timestamp, profile)
    return _deep_copy(profile)


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


def resource_baselines(profile: Mapping[str, Any] | None) -> dict[str, float]:
    """Convert local specifications into conservative Bayesian prior means."""
    source = profile if isinstance(profile, Mapping) else {}
    resources = source.get("resources") if isinstance(source.get("resources"), Mapping) else {}
    benchmarks = source.get("benchmarks") if isinstance(source.get("benchmarks"), Mapping) else {}

    def saturating(value: Any, reference: float) -> float:
        measured = max(0.0, float(value or 0.0))
        return measured / (measured + max(1.0, reference))

    compute = benchmarks.get("compute") if isinstance(benchmarks.get("compute"), Mapping) else {}
    verify = benchmarks.get("verify") if isinstance(benchmarks.get("verify"), Mapping) else {}
    storage_benchmark = benchmarks.get("storage") if isinstance(benchmarks.get("storage"), Mapping) else {}
    cpu = resources.get("cpu") if isinstance(resources.get("cpu"), Mapping) else {}
    memory = resources.get("memory") if isinstance(resources.get("memory"), Mapping) else {}
    storage = resources.get("storage") if isinstance(resources.get("storage"), Mapping) else {}
    storage_speed = (
        float(storage_benchmark.get("read_bytes_s", 0.0) or 0.0)
        + float(storage_benchmark.get("write_bytes_s", 0.0) or 0.0)
    ) / 2.0
    delegation = (
        saturating(cpu.get("logical_count", 0), 8.0)
        + saturating(memory.get("total_bytes", 0), 16.0 * 1024.0 * 1024.0 * 1024.0)
    ) / 2.0
    storage_capacity = saturating(storage.get("free_bytes", 0), 100.0 * 1024.0 * 1024.0 * 1024.0)
    return {
        "connection": 0.5,
        "storage": (saturating(storage_speed, 200.0 * 1024.0 * 1024.0) + storage_capacity) / 2.0,
        "compute": saturating(compute.get("throughput_bytes_s", 0), 100.0 * 1024.0 * 1024.0),
        "verify": saturating(verify.get("throughput_bytes_s", 0), 100.0 * 1024.0 * 1024.0),
        "delegation": delegation,
    }


class DualMemoryBayes:
    """Five independent Beta reputations with fast and durable memories."""

    def __init__(self, state: Mapping[str, Any] | None = None, *, baselines: Mapping[str, float] | None = None) -> None:
        source = state if isinstance(state, Mapping) else {}
        dimensions = source.get("dimensions") if isinstance(source.get("dimensions"), Mapping) else {}
        baseline_values = baselines if isinstance(baselines, Mapping) else {}
        self._dimensions: dict[str, dict[str, dict[str, float]]] = {}
        for dimension in RESOURCE_DIMENSIONS:
            saved = dimensions.get(dimension) if isinstance(dimensions.get(dimension), Mapping) else {}
            baseline = max(0.0, min(1.0, float(baseline_values.get(dimension, 0.5) or 0.0)))
            self._dimensions[dimension] = {
                "short_term": self._load_memory(saved.get("short_term"), baseline),
                "long_term": self._load_memory(saved.get("long_term"), baseline),
            }

    @staticmethod
    def _load_memory(value: Any, baseline: float) -> dict[str, float]:
        source = value if isinstance(value, Mapping) else {}
        has_posterior = "alpha" in source and "beta" in source
        initial_alpha = PRIOR_ALPHA + (2.0 * baseline) if not has_posterior else PRIOR_ALPHA
        initial_beta = PRIOR_BETA + (2.0 * (1.0 - baseline)) if not has_posterior else PRIOR_BETA
        return {
            "alpha": max(PRIOR_ALPHA, float(source.get("alpha", initial_alpha) or initial_alpha)),
            "beta": max(PRIOR_BETA, float(source.get("beta", initial_beta) or initial_beta)),
            "last_updated_unix": max(0.0, float(source.get("last_updated_unix", 0.0) or 0.0)),
        }

    @staticmethod
    def _decay(memory: dict[str, float], now: float, half_life_s: float) -> None:
        last = float(memory.get("last_updated_unix", 0.0) or 0.0)
        if last <= 0.0:
            memory["last_updated_unix"] = now
            return
        elapsed = max(0.0, now - last)
        factor = math.pow(0.5, elapsed / max(1.0, half_life_s))
        memory["alpha"] = PRIOR_ALPHA + (memory["alpha"] - PRIOR_ALPHA) * factor
        memory["beta"] = PRIOR_BETA + (memory["beta"] - PRIOR_BETA) * factor
        memory["last_updated_unix"] = now

    def observe(
        self,
        dimension: str,
        success: bool,
        *,
        weight: float = 1.0,
        event_class: str = "verified",
        now: float | None = None,
    ) -> None:
        if dimension not in RESOURCE_DIMENSIONS:
            raise ValueError(f"unsupported_resource_dimension:{dimension}")
        timestamp = time.time() if now is None else float(now)
        memories = self._dimensions[dimension]
        self._decay(memories["short_term"], timestamp, SHORT_HALF_LIFE_S)
        self._decay(memories["long_term"], timestamp, LONG_HALF_LIFE_S)
        base_weight = max(0.0, min(100.0, float(weight)))
        event = str(event_class or "verified").lower()
        if event == "transient":
            factors = (1.0, 0.05)
        elif event == "integrity":
            factors = (1.5, 4.0)
        else:
            factors = (0.75, 1.0)
        for name, factor in zip(("short_term", "long_term"), factors):
            memory = memories[name]
            key = "alpha" if success else "beta"
            memory[key] += base_weight * factor

    @staticmethod
    def _summary(memory: Mapping[str, float]) -> dict[str, float]:
        alpha = float(memory["alpha"])
        beta = float(memory["beta"])
        total = max(alpha + beta, 1e-9)
        mean = alpha / total
        variance = (alpha * beta) / ((total * total) * (total + 1.0))
        margin = 1.96 * math.sqrt(max(0.0, variance))
        return {
            "mean": round(mean, 6),
            "lower_bound": round(max(0.0, mean - margin), 6),
            "upper_bound": round(min(1.0, mean + margin), 6),
            "evidence": round(max(0.0, total - PRIOR_ALPHA - PRIOR_BETA), 6),
        }

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        timestamp = time.time() if now is None else float(now)
        result: dict[str, Any] = {"schema": REPUTATION_SCHEMA, "observed_utc": _utc_now(timestamp), "dimensions": {}}
        for dimension, memories in self._dimensions.items():
            self._decay(memories["short_term"], timestamp, SHORT_HALF_LIFE_S)
            self._decay(memories["long_term"], timestamp, LONG_HALF_LIFE_S)
            short = self._summary(memories["short_term"])
            long = self._summary(memories["long_term"])
            result["dimensions"][dimension] = {
                "short_term": short,
                "long_term": long,
                "combined": {
                    "mean": round((short["mean"] * 0.35) + (long["mean"] * 0.65), 6),
                    "lower_bound": round((short["lower_bound"] * 0.35) + (long["lower_bound"] * 0.65), 6),
                    "evidence": round(short["evidence"] + long["evidence"], 6),
                },
            }
        return result

    def export_state(self) -> dict[str, Any]:
        return {
            "schema": REPUTATION_SCHEMA,
            "dimensions": _deep_copy(self._dimensions),
            "short_half_life_s": SHORT_HALF_LIFE_S,
            "long_half_life_s": LONG_HALF_LIFE_S,
        }
