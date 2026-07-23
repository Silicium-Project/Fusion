from __future__ import annotations

import ctypes
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any


def _filetime_value(value: Any) -> int:
    return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)


def _system_cpu_times() -> tuple[int, int] | None:
    if os.name == "nt":
        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]

        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
        return _filetime_value(idle), _filetime_value(kernel) + _filetime_value(user)

    try:
        fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
        values = [int(value) for value in fields]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return idle, sum(values)
    except (OSError, ValueError, IndexError):
        return None


def _process_memory() -> tuple[int, int]:
    if os.name == "nt":
        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
            ctypes.c_ulong,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)
        return 0, 0

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        fields = Path("/proc/self/statm").read_text(encoding="ascii").split()
        rss = int(fields[1]) * page_size
    except (OSError, ValueError, IndexError):
        rss = 0
    peak = rss
    try:
        import resource

        raw_peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        peak = raw_peak if sys.platform == "darwin" else raw_peak * 1024
    except (ImportError, ValueError):
        pass
    return rss, peak


def _system_memory() -> tuple[int, int]:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys), int(status.ullAvailPhys)
        return 0, 0

    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
        return values.get("MemTotal", 0), values.get("MemAvailable", 0)
    except (OSError, ValueError, IndexError):
        return 0, 0


class RuntimeTelemetrySampler:
    """Portable, dependency-free node and host resource sampler."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.started_monotonic = time.monotonic()
        self.started_utc = time.time()
        self._last_monotonic = self.started_monotonic
        process_times = os.times()
        self._last_process_cpu = float(process_times.user + process_times.system)
        self._last_system_cpu = _system_cpu_times()
        self._lock = threading.Lock()
        self._last_snapshot: dict[str, Any] = {}

    def sample(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            interval = max(0.001, now - self._last_monotonic)
            cpu_count = max(1, int(os.cpu_count() or 1))
            process_times = os.times()
            process_cpu = float(process_times.user + process_times.system)
            process_delta = max(0.0, process_cpu - self._last_process_cpu)
            process_cpu_one_core = min(100.0 * cpu_count, 100.0 * process_delta / interval)
            process_cpu_normalized = min(100.0, process_cpu_one_core / cpu_count)

            system_cpu = _system_cpu_times()
            system_cpu_percent = 0.0
            if system_cpu is not None and self._last_system_cpu is not None:
                idle_delta = max(0, system_cpu[0] - self._last_system_cpu[0])
                total_delta = max(0, system_cpu[1] - self._last_system_cpu[1])
                if total_delta:
                    system_cpu_percent = max(
                        0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta))
                    )

            rss, peak_rss = _process_memory()
            memory_total, memory_available = _system_memory()
            memory_used = max(0, memory_total - memory_available)
            memory_percent = (
                100.0 * memory_used / memory_total if memory_total > 0 else 0.0
            )
            try:
                disk = shutil.disk_usage(self.storage_path)
                disk_total = int(disk.total)
                disk_free = int(disk.free)
            except OSError:
                disk_total = 0
                disk_free = 0

            try:
                load_average = [round(float(value), 3) for value in os.getloadavg()]
            except (AttributeError, OSError):
                load_average = []

            snapshot = {
                "schema": "silicium.runtime-telemetry.v1",
                "sampled_unix": int(time.time()),
                "sample_interval_ms": round(interval * 1000),
                "node_uptime_seconds": round(now - self.started_monotonic, 3),
                "process_cpu_percent": round(process_cpu_normalized, 2),
                "process_cpu_percent_one_core": round(process_cpu_one_core, 2),
                "process_cpu_seconds": round(process_cpu, 3),
                "process_rss_bytes": rss,
                "process_peak_rss_bytes": peak_rss,
                "system_cpu_percent": round(system_cpu_percent, 2),
                "system_memory_total_bytes": memory_total,
                "system_memory_available_bytes": memory_available,
                "system_memory_used_bytes": memory_used,
                "system_memory_percent": round(memory_percent, 2),
                "logical_cpu_count": cpu_count,
                "python_thread_count": threading.active_count(),
                "load_average": load_average,
                "storage_total_bytes": disk_total,
                "storage_free_bytes": disk_free,
                "storage_used_percent": round(
                    100.0 * (disk_total - disk_free) / disk_total, 2
                )
                if disk_total
                else 0.0,
            }
            self._last_monotonic = now
            self._last_process_cpu = process_cpu
            self._last_system_cpu = system_cpu
            self._last_snapshot = snapshot
            return dict(snapshot)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last_snapshot)
