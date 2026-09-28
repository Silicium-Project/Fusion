"""Entry point: verify a rendered tile (delegates to raytracer_workload)."""
from __future__ import annotations

import sys

from raytracer_workload import main


if __name__ == "__main__":
    raise SystemExit(main(["verify", *sys.argv[1:]]))
