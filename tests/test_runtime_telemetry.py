from __future__ import annotations

import time

from tools.runtime_telemetry import RuntimeTelemetrySampler


def test_runtime_sampler_reports_cpu_memory_disk_and_uptime(tmp_path):
    sampler = RuntimeTelemetrySampler(tmp_path)
    first = sampler.sample()
    time.sleep(0.01)
    second = sampler.sample()

    assert second["schema"] == "silicium.runtime-telemetry.v1"
    assert second["sample_interval_ms"] >= 1
    assert second["node_uptime_seconds"] >= first["node_uptime_seconds"]
    assert 0 <= second["process_cpu_percent"] <= 100
    assert 0 <= second["system_cpu_percent"] <= 100
    assert second["logical_cpu_count"] >= 1
    assert second["python_thread_count"] >= 1
    assert second["process_rss_bytes"] >= 0
    assert second["system_memory_total_bytes"] >= second["system_memory_available_bytes"]
    assert second["storage_total_bytes"] >= second["storage_free_bytes"]


def test_runtime_sampler_snapshot_is_a_copy(tmp_path):
    sampler = RuntimeTelemetrySampler(tmp_path)
    sampler.sample()
    snapshot = sampler.snapshot()
    snapshot["system_cpu_percent"] = -1

    assert sampler.snapshot()["system_cpu_percent"] >= 0
