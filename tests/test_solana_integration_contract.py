from __future__ import annotations

from pathlib import Path

from tools.dev.release import solana_devnet_preflight


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PROGRAM_ID = "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"


def test_preflight_accepts_an_executable_program(monkeypatch) -> None:
    def fake_rpc(_rpc: str, method: str, _params=None):
        if method == "getVersion":
            return {"solana-core": "test"}
        if method == "getSlot":
            return 123
        if method == "getAccountInfo":
            return {
                "value": {
                    "executable": True,
                    "owner": "BPFLoaderUpgradeab1e11111111111111111111111",
                    "lamports": 1,
                    "space": 36,
                }
            }
        raise AssertionError(method)

    monkeypatch.setattr(solana_devnet_preflight, "rpc_call", fake_rpc)
    report = solana_devnet_preflight.build_report("https://rpc.test", CANONICAL_PROGRAM_ID)
    assert report["verified"] is True
    assert report["program_id"] == CANONICAL_PROGRAM_ID
    assert report["program_account"]["executable"] is True


def test_solana_write_flow_reconciles_artifact_and_finalizes_job() -> None:
    trace = (REPO_ROOT / "solana-layer" / "scripts" / "devnet_trace_fragments.ts").read_text(encoding="utf-8")
    minimal = (REPO_ROOT / "solana-layer" / "scripts" / "devnet_minimal_job_flow.ts").read_text(encoding="utf-8")
    assert "SILICIUM_CHAIN_RESULT_HASH" in trace
    assert "hash_match" in trace
    assert ".finalizeJob(" in minimal
    assert "claim_reward_1" in minimal and "claim_reward_2" in minimal


def test_all_runtime_program_defaults_use_the_canonical_id() -> None:
    paths = [
        REPO_ROOT / "tools" / "network_node.py",
        REPO_ROOT / "workloads" / "raytracer" / "run_network_job.py",
        REPO_ROOT / "silicium-layer-dashboard" / "src" / "lib" / "solana.ts",
        REPO_ROOT / "solana-layer" / "silicium-sdk" / "src" / "index.ts",
    ]
    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert CANONICAL_PROGRAM_ID in content, path
        assert "4FPGViycNEGCtwnNs3NN2pPQu9ziTch8o9zkVc2VnKVP" not in content, path
        assert "AkAFDh9CpGHAoM7gL7zAZxdCJVV6bheBTidZEyZ4BMpA" not in content, path
