"""Entry point: reassemble rendered tiles into the final image (delegates to raytracer_workload)."""
from __future__ import annotations

import sys

from raytracer_workload import main


if __name__ == "__main__":
    raise SystemExit(main(["reassemble", *sys.argv[1:]]))
