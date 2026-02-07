#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_NAMESPACES = [
    "core.",
    "cli.",
    "tui.",
    "worker.",
    "executor.",
    "splitter.",
    "viewer.",
    "infra.",
    "workload.",
]


def load_locale(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level must be object")
    meta = raw.get("meta")
    messages = raw.get("messages")
    if not isinstance(meta, dict):
        raise ValueError(f"{path}: missing meta object")
    if not isinstance(messages, dict):
        raise ValueError(f"{path}: missing messages object")
    locale = meta.get("locale")
    if not isinstance(locale, str) or not locale:
        raise ValueError(f"{path}: meta.locale must be non-empty string")
    if path.stem != locale:
        raise ValueError(f"{path}: filename must match meta.locale")
    for key, value in messages.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{path}: invalid message key")
        if not isinstance(value, str):
            raise ValueError(f"{path}: message value for {key} must be string")
    return raw


def locale_report(locales_dir: Path, reference: str) -> dict[str, Any]:
    locale_files = sorted(locales_dir.glob("*.json"))
    if not locale_files:
        return {
            "errors": ["no locale files found"],
            "locales": {},
            "missing_keys": {},
            "extra_keys": {},
            "namespace_coverage": {},
        }

    data_by_locale: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path in locale_files:
        try:
            data = load_locale(path)
        except Exception as exc:
            errors.append(str(exc))
            continue
        locale_name = str(data["meta"]["locale"])
        data_by_locale[locale_name] = data

    if reference not in data_by_locale:
        errors.append(f"reference locale not found: {reference}")
        return {
            "errors": errors,
            "locales": {},
            "missing_keys": {},
            "extra_keys": {},
            "namespace_coverage": {},
        }

    reference_keys = set(data_by_locale[reference]["messages"].keys())
    missing_keys: dict[str, list[str]] = {}
    extra_keys: dict[str, list[str]] = {}
    namespace_coverage: dict[str, dict[str, bool]] = {}

    for locale_name, data in data_by_locale.items():
        keys = set(data["messages"].keys())
        missing = sorted(reference_keys - keys)
        extras = sorted(keys - reference_keys)
        missing_keys[locale_name] = missing
        extra_keys[locale_name] = extras
        coverage = {}
        for namespace in REQUIRED_NAMESPACES:
            coverage[namespace] = any(key.startswith(namespace) for key in keys)
        namespace_coverage[locale_name] = coverage

    return {
        "errors": errors,
        "locales": sorted(data_by_locale.keys()),
        "reference": reference,
        "missing_keys": missing_keys,
        "extra_keys": extra_keys,
        "namespace_coverage": namespace_coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate i18n locale packs.")
    parser.add_argument(
        "--locales-dir",
        default="i18n/locales",
        help="Path to locale JSON files.",
    )
    parser.add_argument(
        "--reference",
        default="en-US",
        help="Reference locale key set.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on errors/missing/extra/namespace coverage gaps.",
    )
    args = parser.parse_args()

    report = locale_report(Path(args.locales_dir).resolve(), args.reference)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Locales: {', '.join(report.get('locales', [])) or '-'}")
        if report["errors"]:
            print("Errors:")
            for item in report["errors"]:
                print(f"  - {item}")
        for locale_name in report.get("locales", []):
            missing = report["missing_keys"].get(locale_name, [])
            extra = report["extra_keys"].get(locale_name, [])
            print(
                f"{locale_name}: missing={len(missing)} extra={len(extra)}"
            )

    if not args.strict:
        return

    has_missing = any(report["missing_keys"].get(locale_name) for locale_name in report.get("locales", []))
    has_extra = any(report["extra_keys"].get(locale_name) for locale_name in report.get("locales", []))
    has_namespace_gaps = any(
        not all(coverage.values())
        for coverage in report.get("namespace_coverage", {}).values()
    )
    if report["errors"] or has_missing or has_extra or has_namespace_gaps:
        sys.exit(1)


if __name__ == "__main__":
    main()
