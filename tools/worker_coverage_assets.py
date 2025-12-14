#!/usr/bin/env python3
"""Generate worker coverage badges and optionally refresh the README snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


COLOR_HEX = {
    "brightgreen": "#4c1",
    "green": "#97CA00",
    "yellowgreen": "#a4a61d",
    "yellow": "#dfb317",
    "orange": "#fe7d37",
    "red": "#e05d44",
}


def rate(covered: float, total: float) -> float:
    return 0.0 if total == 0 else covered / total * 100.0


def coverage_percent(summary: dict, prefix: str) -> float:
    covered = summary.get(f"{prefix}_covered")
    total = summary.get(f"{prefix}_total")
    percent = summary.get(f"{prefix}_percent")

    if covered is not None and total is not None:
        try:
            return rate(float(covered), float(total))
        except (TypeError, ValueError):
            pass

    if percent is None:
        return 0.0

    try:
        return float(percent)
    except (TypeError, ValueError):
        return 0.0


def pick_color(ratio: float) -> str:
    if ratio >= 90:
        return "brightgreen"
    if ratio >= 80:
        return "green"
    if ratio >= 70:
        return "yellowgreen"
    if ratio >= 60:
        return "yellow"
    if ratio >= 50:
        return "orange"
    return "red"


def write_badge_files(output_dir: Path, label: str, ratio: float, color: str) -> None:
    badge = {
        "schemaVersion": 1,
        "label": label,
        "message": f"{ratio:.1f}%",
        "color": color,
    }
    (output_dir / "badge.json").write_text(json.dumps(badge), encoding="utf-8")

    color_hex = COLOR_HEX.get(color, COLOR_HEX["red"])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="162" height="20" role="img" aria-label="{label}: {ratio:.1f}%">
  <title>{label}: {ratio:.1f}%</title>
  <linearGradient id="smooth" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <rect rx="3" width="162" height="20" fill="#555"/>
  <rect rx="3" x="100" width="62" height="20" fill="{color_hex}"/>
  <rect rx="3" width="162" height="20" fill="url(#smooth)"/>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="50" y="15">{label}</text>
    <text x="130" y="15">{ratio:.1f}%</text>
  </g>
</svg>"""
    (output_dir / "badge.svg").write_text(svg, encoding="utf-8")


def update_readme(readme_path: Path, start_marker: str, end_marker: str, snippet: str) -> None:
    content = readme_path.read_text(encoding="utf-8")
    if start_marker not in content or end_marker not in content:
        raise RuntimeError("Coverage markers not found in README.md")

    before, rest = content.split(start_marker, 1)
    mid, after = rest.split(end_marker, 1)
    new_content = f"{before}{start_marker}\n{snippet}\n{end_marker}{after}"
    readme_path.write_text(new_content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path, help="Path to coverage-summary.json")
    parser.add_argument("--output", required=True, type=Path, help="Directory where badge files are written")
    parser.add_argument("--label", default="worker coverage", help="Label used in badge files")
    parser.add_argument("--readme", type=Path, help="Optional README path to update snapshot markers")
    parser.add_argument(
        "--start-marker",
        default="<!-- worker-coverage:start -->",
        help="Marker that precedes the snapshot section in the README",
    )
    parser.add_argument(
        "--end-marker",
        default="<!-- worker-coverage:end -->",
        help="Marker that follows the snapshot section in the README",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary_path = args.summary
    output_dir = args.output

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    line_pct = coverage_percent(summary, "line")
    func_pct = coverage_percent(summary, "function")
    branch_pct = coverage_percent(summary, "branch")

    output_dir.mkdir(parents=True, exist_ok=True)
    color = pick_color(line_pct)
    write_badge_files(output_dir, args.label, line_pct, color)

    if args.readme:
        snippet = (
            f"- Snapshot (auto) : lignes {line_pct:.1f} %, "
            f"fonctions {func_pct:.1f} %, branches {branch_pct:.1f} %"
        )
        update_readme(args.readme, args.start_marker, args.end_marker, snippet)


if __name__ == "__main__":
    main()
