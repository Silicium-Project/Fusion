from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CONTRACT_PATH = Path(__file__).with_name("channels.json")
VALID_CHANNELS = ("dev", "prod")


def _load_contract() -> dict[str, Any]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("channels"), dict):
        raise ValueError("release channel contract is malformed")
    return payload


def normalize(channel: str | None) -> str:
    value = str(channel or "").strip().lower()
    if value not in VALID_CHANNELS:
        raise ValueError(f"unsupported release channel: {channel!r}")
    return value


def infer_from_ref(ref: str | None) -> str:
    value = str(ref or "").strip()
    if value.startswith("refs/heads/"):
        value = value.removeprefix("refs/heads/")
    if value.startswith("refs/tags/"):
        value = value.removeprefix("refs/tags/")
    return "prod" if value == "main" or value.startswith("v") else "dev"


def metadata(channel: str | None) -> dict[str, Any]:
    normalized = normalize(channel)
    payload = _load_contract()
    result = payload["channels"].get(normalized)
    if not isinstance(result, dict):
        raise ValueError(f"missing release channel definition: {normalized}")
    return {"channel": normalized, **result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and inspect a Silicium release channel.")
    parser.add_argument("channel", nargs="?", default="dev")
    parser.add_argument("--ref", default="", help="Infer the channel from a Git ref instead.")
    parser.add_argument("--field", default="", help="Print one scalar field from the channel contract.")
    args = parser.parse_args()
    channel = infer_from_ref(args.ref) if args.ref else normalize(args.channel)
    payload = metadata(channel)
    if args.field:
        value = payload.get(args.field)
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"channel field is not scalar or is missing: {args.field}")
        print(value)
    else:
        print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
