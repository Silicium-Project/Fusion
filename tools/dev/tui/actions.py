from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = [sys.executable, str(REPO_ROOT / "silicium")]
LOG_DIR = REPO_ROOT / ".silicium" / "logs"


@dataclass(frozen=True)
class ActionSpec:
    key: str
    label: str
    args: list[str]
    description: str
    resources: frozenset[str] = frozenset()
    runner_sensitive: bool = False
    runner_resources: dict[str, frozenset[str]] | None = None

    def command(self, runner_mode: str) -> list[str]:
        cmd = CLI + self.args
        if self.runner_sensitive:
            cmd += ["--runner", runner_mode]
        return cmd

    def resources_for(self, runner_mode: str) -> set[str]:
        resources = set(self.resources)
        if self.runner_sensitive and self.runner_resources:
            resources.update(self.runner_resources.get(runner_mode, set()))
        return resources


def build_actions() -> list[ActionSpec]:
    return [
        ActionSpec(
            key="status",
            label="Status (docker compose)",
            args=["status"],
            description="Show compose services status for the current project.",
            resources=frozenset({"docker"}),
        ),
        ActionSpec(
            key="start_localnet",
            label="Start localnet",
            args=["start", "localnet"],
            description="Start localnet validator with proxy if configured.",
            resources=frozenset({"docker", "network"}),
        ),
        ActionSpec(
            key="stop_all",
            label="Stop all services",
            args=["stop", "all"],
            description="Stop all compose services for the project.",
            resources=frozenset({"docker"}),
        ),
        ActionSpec(
            key="logs_proxy",
            label="Logs (proxy)",
            args=["logs", "silicium-proxy"],
            description="Fetch logs for the proxy service.",
            resources=frozenset({"docker"}),
        ),
        ActionSpec(
            key="workloads",
            label="List workloads",
            args=["workload", "list"],
            description="List known workload manifests.",
            resources=frozenset({"io"}),
        ),
        ActionSpec(
            key="check_quick",
            label="Core check (quick)",
            args=["check"],
            description="Run the quick core check flow (may use Docker/WSL).",
            resources=frozenset({"cpu"}),
            runner_sensitive=True,
            runner_resources={
                "auto": frozenset({"docker"}),
                "docker": frozenset({"docker"}),
                "wsl": frozenset({"wsl"}),
            },
        ),
        ActionSpec(
            key="clean_cache",
            label="Clean cache",
            args=["clean", "cache"],
            description="Clean build caches and temporary artifacts.",
            resources=frozenset({"io"}),
        ),
    ]
