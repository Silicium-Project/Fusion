from __future__ import annotations

import sys
from pathlib import Path

NETWORK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NETWORK_ROOT))

from workloads.render3d.render3d_workload import *  # noqa: F401,F403,E402
from workloads.render3d.render3d_workload import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
