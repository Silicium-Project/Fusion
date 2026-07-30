from __future__ import annotations

import time
from types import SimpleNamespace

from tools import network_node
from tools.resource_intelligence import DualMemoryBayes, RESOURCE_DIMENSIONS, build_resource_profile, resource_baselines


def test_resource_profile_is_bounded_versioned_and_cached(tmp_path) -> None:
    started = time.perf_counter()
    first = build_resource_profile(tmp_path, refresh_s=300)
    elapsed = time.perf_counter() - started
    second = build_resource_profile(tmp_path, refresh_s=300)

    assert elapsed < 2.0
    assert first["schema"] == "silicium.resource-profile.v1"
    assert first["resources"]["cpu"]["logical_count"] >= 1
    assert first["resources"]["storage"]["total_bytes"] > 0
    assert first["benchmarks"]["compute"]["throughput_bytes_s"] > 0
    assert first["benchmarks"]["storage"]["verified"] is True
    assert second == first


def test_transient_failure_changes_short_memory_more_than_long_memory() -> None:
    model = DualMemoryBayes()
    model.observe("connection", False, event_class="transient", now=100.0)
    connection = model.snapshot(now=100.0)["dimensions"]["connection"]

    assert connection["short_term"]["mean"] < connection["long_term"]["mean"]
    assert connection["short_term"]["evidence"] > connection["long_term"]["evidence"]


def test_integrity_failure_is_remembered_primarily_long_term() -> None:
    model = DualMemoryBayes()
    model.observe("verify", False, event_class="integrity", now=100.0)
    verification = model.snapshot(now=100.0)["dimensions"]["verify"]

    assert verification["long_term"]["mean"] < verification["short_term"]["mean"]
    assert verification["long_term"]["evidence"] > verification["short_term"]["evidence"]


def test_resource_dimensions_are_independent() -> None:
    model = DualMemoryBayes()
    for _ in range(8):
        model.observe("compute", True, event_class="verified", now=100.0)
    dimensions = model.snapshot(now=100.0)["dimensions"]

    assert set(dimensions) == set(RESOURCE_DIMENSIONS)
    assert dimensions["compute"]["combined"]["mean"] > dimensions["storage"]["combined"]["mean"]
    assert dimensions["storage"]["combined"]["mean"] == 0.5


def test_benchmarks_seed_conservative_resource_priors(tmp_path) -> None:
    profile = build_resource_profile(tmp_path)
    baselines = resource_baselines(profile)
    dimensions = DualMemoryBayes(baselines=baselines).snapshot()["dimensions"]

    assert set(baselines) == set(RESOURCE_DIMENSIONS)
    assert 0.0 < baselines["compute"] < 1.0
    assert dimensions["compute"]["combined"]["evidence"] == 4.0
    assert 0.33 <= dimensions["compute"]["combined"]["mean"] <= 0.67


def test_reputation_store_persists_dual_memory(tmp_path) -> None:
    path = tmp_path / "reputation.json"
    store = network_node.ReputationStore(path)
    store.observe_resource("storage", True, event_class="verified")
    evidence = store.resource_snapshot()["dimensions"]["storage"]["combined"]["evidence"]

    reloaded = network_node.ReputationStore(path)
    reloaded_evidence = reloaded.resource_snapshot()["dimensions"]["storage"]["combined"]["evidence"]
    assert abs(reloaded_evidence - evidence) < 0.001


def test_scheduler_uses_resource_lower_confidence_bound() -> None:
    config = SimpleNamespace(
        scheduler_onchain_weight=0.0,
        scheduler_offchain_weight=1.0,
        scheduler_capacity_weight=0.0,
    )
    scheduler = SimpleNamespace(config=config)
    reliable = DualMemoryBayes()
    uncertain = DualMemoryBayes()
    for _ in range(20):
        reliable.observe("compute", True, now=100.0)
        reliable.observe("connection", True, now=100.0)
        uncertain.observe("compute", False, now=100.0)
        uncertain.observe("connection", False, now=100.0)
    common = {"capacity": {"cpu_count": 8, "disk_free_bytes": 10_000}, "reputation_score": 50.0}

    reliable_score = network_node.PeerNetwork._peer_score(
        scheduler, {**common, "resource_reputation": reliable.snapshot(now=100.0)}, {"compute"}
    )
    uncertain_score = network_node.PeerNetwork._peer_score(
        scheduler, {**common, "resource_reputation": uncertain.snapshot(now=100.0)}, {"compute"}
    )

    assert reliable_score > uncertain_score


def test_uptime_dimension_and_corroboration_scaling() -> None:
    model = DualMemoryBayes()
    # 24 hours uptime, 3 corroborated peers
    w1 = model.observe_uptime(86400, corroborated_peer_count=3, now=100.0)
    # Self-reported only
    w2 = model.observe_uptime(86400, self_reported_only=True, now=100.0)

    assert w1 > w2
    snapshot = model.snapshot(now=100.0)["dimensions"]["uptime"]
    assert snapshot["combined"]["evidence"] > 0.0
    assert snapshot["combined"]["mean"] > 0.5

