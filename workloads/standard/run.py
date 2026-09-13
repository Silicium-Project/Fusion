#!/usr/bin/env python3
"""Run a built-in workload against files, for local validation and CI."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from .standard_workloads import run_standard_workload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    input_bytes = args.input.read_bytes()

    def put_output(data: bytes) -> dict[str, object]:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        return {
            "protocol": "file",
            "content_id": str(args.output),
            "hash": f"sha256:{digest}",
            "size_bytes": len(data),
        }

    result = run_standard_workload(
        args.workload,
        {},
        input_bytes,
        {"source": "file", "path": str(args.input), "size_bytes": len(input_bytes)},
        put_output,
    )
    if result is None:
        parser.error(f"unsupported built-in workload: {args.workload}")
    print(result["result_hash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
