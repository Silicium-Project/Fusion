"""Entry point: split a scene into tiles (delegates to raytracer_workload)."""
from __future__ import annotations

import sys

from raytracer_workload import main


if __name__ == "__main__":
    raise SystemExit(main(["split", *sys.argv[1:]]))
