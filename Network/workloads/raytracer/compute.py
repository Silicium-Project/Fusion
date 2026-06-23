from __future__ import annotations

import sys

from raytracer_workload import main


if __name__ == "__main__":
    raise SystemExit(main(["compute", *sys.argv[1:]]))
