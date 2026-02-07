#!/usr/bin/env python3
"""Generate worker coverage badges, summary HTML, and optionally refresh README."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Optional


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


def clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, value))


def chart_card(label: str, pct: float) -> str:
    pct = clamp_pct(pct)
    radius = 42
    circumference = 2 * math.pi * radius
    offset = circumference * (1 - pct / 100)
    color = COLOR_HEX.get(pick_color(pct), COLOR_HEX["red"])
    return f"""<div class="chart-card">
  <svg viewBox="0 0 120 120" role="img" aria-label="{label}: {pct:.1f}%">
    <circle class="track" cx="60" cy="60" r="{radius}" />
    <circle class="progress" cx="60" cy="60" r="{radius}" stroke="{color}" stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}" transform="rotate(-90 60 60)" />
    <text x="60" y="64" class="value">{pct:.1f}%</text>
  </svg>
  <div class="chart-label">{label}</div>
</div>"""


def summary_html(title: str, line_pct: float, func_pct: float, branch_pct: float, full_report: str, accent: str) -> str:
    accent_hex = COLOR_HEX.get(accent, COLOR_HEX["red"])
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --accent: {accent_hex};
      --bg: #0f172a;
      --card: #111827;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --border: #1f2937;
      --chart-track: #1f2937;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
      background: radial-gradient(circle at 20% 20%, rgba(37,99,235,0.1), transparent 30%), radial-gradient(circle at 80% 0%, rgba(16,185,129,0.12), transparent 35%), var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 32px 16px;
    }}
    .shell {{
      width: min(1100px, 100%);
      background: linear-gradient(145deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
      border: 1px solid var(--border);
      box-shadow: 0 10px 60px rgba(0,0,0,0.35);
      border-radius: 18px;
      padding: 28px;
      backdrop-filter: blur(10px);
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 20px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      letter-spacing: -0.01em;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(255,255,255,0.06);
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 8px 14px;
      color: var(--muted);
      font-size: 13px;
    }}
    .pill::before {{
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 12px var(--accent);
    }}
    a {{
      color: var(--text);
    }}
    .charts {{
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    }}
    .chart-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      text-align: center;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
    }}
    svg {{
      width: 160px;
      height: 160px;
    }}
    .track {{
      fill: none;
      stroke: var(--chart-track);
      stroke-width: 14;
    }}
    .progress {{
      fill: none;
      stroke-width: 14;
      stroke-linecap: round;
      filter: drop-shadow(0 0 8px rgba(34,197,94,0.35));
    }}
    .value {{
      font-size: 22px;
      fill: var(--text);
      font-weight: 700;
      text-anchor: middle;
    }}
    .chart-label {{
      margin-top: 10px;
      font-weight: 600;
      color: var(--muted);
      letter-spacing: 0.01em;
    }}
    .links {{
      margin-top: 16px;
      font-size: 14px;
      color: var(--muted);
    }}
    .links a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
    .links a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <h1>{title}</h1>
        <div class="pill">DerniÃ¨re exÃ©cution Â· couverture</div>
      </div>
    </header>
    <section class="charts">
      {chart_card("Lignes", line_pct)}
      {chart_card("Fonctions", func_pct)}
      {chart_card("Branches", branch_pct)}
    </section>
    <div class="links">
      Rapport complet : <a href="{full_report}">coverage-full.html</a>
    </div>
  </div>
</body>
</html>"""


def write_summary_html(destination: Path, title: str, line_pct: float, func_pct: float, branch_pct: float, full_report: str, accent: str) -> None:
    destination.write_text(summary_html(title, line_pct, func_pct, branch_pct, full_report, accent), encoding="utf-8")


def snapshot_svg(line_pct: float, func_pct: float, branch_pct: float) -> str:
    def donut(cx: int, cy: int, pct: float, grad_id: str) -> str:
        color = COLOR_HEX.get(pick_color(pct), COLOR_HEX["red"])
        r = 32
        circ = 2 * math.pi * r
        pct = clamp_pct(pct)
        offset = circ * (1 - pct / 100)
        return (
            f'<circle class="track" cx="{cx}" cy="{cy}" r="{r}" />'
            f'<circle class="arc" cx="{cx}" cy="{cy}" r="{r}" '
            f'stroke="{color}" stroke-dasharray="{circ:.2f}" stroke-dashoffset="{offset:.2f}" transform="rotate(-90 {cx} {cy})" />'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 150" role="img" aria-label="Worker coverage snapshot">
  <style>
    .bg {{ fill: #0f172a; }}
    .card {{ fill: #111827; stroke: #1f2937; stroke-width: 1; }}
    .track {{ fill: none; stroke: #1f2937; stroke-width: 12; }}
    .arc {{ fill: none; stroke-width: 12; stroke-linecap: round; }}
    .label {{ fill: #cbd5e1; font-family: "Inter", "Segoe UI", sans-serif; font-size: 13px; text-anchor: middle; }}
    .value {{ fill: #e2e8f0; font-family: "Inter", "Segoe UI", sans-serif; font-size: 16px; font-weight: 700; text-anchor: middle; }}
  </style>
  <rect class="bg" x="0" y="0" width="320" height="150" rx="14" />
  <rect class="card" x="6" y="6" width="308" height="138" rx="12" />
  {donut(60, 70, line_pct, "grad-line")}
  <text class="value" x="60" y="74">{line_pct:.1f}%</text>
  <text class="label" x="60" y="118">Lignes</text>

  {donut(160, 70, func_pct, "grad-func")}
  <text class="value" x="160" y="74">{func_pct:.1f}%</text>
  <text class="label" x="160" y="118">Fonctions</text>

  {donut(260, 70, branch_pct, "grad-branch")}
  <text class="value" x="260" y="74">{branch_pct:.1f}%</text>
  <text class="label" x="260" y="118">Branches</text>
</svg>"""


def write_snapshot(destination: Path, line_pct: float, func_pct: float, branch_pct: float) -> None:
    destination.write_text(snapshot_svg(line_pct, func_pct, branch_pct), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path, help="Path to coverage-summary.json")
    parser.add_argument("--output", required=True, type=Path, help="Directory where badge files are written")
    parser.add_argument("--label", default="worker coverage", help="Label used in badge files")
    parser.add_argument("--readme", type=Path, help="Optional README path to update snapshot markers")
    parser.add_argument("--summary-html", type=Path, help="Optional HTML summary output path")
    parser.add_argument("--full-report", default="coverage-full.html", help="Relative link to the full coverage report")
    parser.add_argument("--snapshot", type=Path, help="Optional snapshot SVG output path (donut charts)")
    parser.add_argument("--readme-snapshot", help="Path to snapshot SVG as referenced from README (relative or absolute)")
    parser.add_argument("--readme-report", help="Path to report HTML as referenced from README")
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

    if args.summary_html:
        write_summary_html(
            args.summary_html,
            args.label.title(),
            line_pct,
            func_pct,
            branch_pct,
            args.full_report,
            color,
        )

    if args.snapshot:
        write_snapshot(args.snapshot, line_pct, func_pct, branch_pct)

    if args.readme:
        readme_snapshot: Optional[str] = None
        if args.readme_snapshot:
            readme_snapshot = args.readme_snapshot
        elif args.snapshot:
            try:
                readme_snapshot = str(args.snapshot.relative_to(args.readme.parent))
            except ValueError:
                readme_snapshot = str(args.snapshot)

        metrics_text = f"Lignes {line_pct:.1f} %, fonctions {func_pct:.1f} %, branches {branch_pct:.1f} %"
        snippet_parts = []
        if readme_snapshot and args.readme_report:
            snippet_parts.append(f"- AperÃ§u : [![worker coverage]({readme_snapshot} \"{metrics_text}\")]({args.readme_report})")
        elif readme_snapshot:
            snippet_parts.append(f"- AperÃ§u : ![worker coverage]({readme_snapshot} \"{metrics_text}\")")
        elif args.readme_report:
            snippet_parts.append(f"- Snapshot (auto) : {metrics_text}")
            snippet_parts.append(f"- AperÃ§u : {args.readme_report}")
        else:
            snippet_parts.append(f"- Snapshot (auto) : {metrics_text}")

        update_readme(args.readme, args.start_marker, args.end_marker, "\n".join(snippet_parts))


if __name__ == "__main__":
    main()
