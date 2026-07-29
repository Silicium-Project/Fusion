#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run(args: list[str]) -> str:
    process = subprocess.run(
        args,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if process.returncode:
        raise RuntimeError(
            f"command failed ({process.returncode}): {' '.join(args)}\n{process.stdout}"
        )
    return process.stdout.strip()


def list_issues(repository: str) -> list[dict[str, Any]]:
    raw = run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "all",
            "--limit",
            "500",
            "--json",
            "number,title,url,state",
        ]
    )
    value = json.loads(raw or "[]")
    if not isinstance(value, list):
        raise TypeError(f"unexpected issue list for {repository}")
    return [item for item in value if isinstance(item, dict)]


def ensure_issue(spec: dict[str, Any]) -> dict[str, Any]:
    repository = str(spec["repository"])
    title = str(spec["title"])
    body = str(spec["body"])
    existing = next(
        (item for item in list_issues(repository) if item.get("title") == title), None
    )
    if existing is not None:
        return {
            "action": "existing",
            "repository": repository,
            "number": int(existing["number"]),
            "title": title,
            "url": str(existing["url"]),
            "state": str(existing["state"]),
        }

    url = run(
        [
            "gh",
            "issue",
            "create",
            "--repo",
            repository,
            "--title",
            title,
            "--body",
            body,
        ]
    )
    return {
        "action": "created",
        "repository": repository,
        "number": int(url.rstrip("/").split("/")[-1]),
        "title": title,
        "url": url,
        "state": "OPEN",
    }


def close_completed(spec: dict[str, Any]) -> dict[str, Any]:
    repository = str(spec["repository"])
    number = int(spec["number"])
    item = json.loads(
        run(
            [
                "gh",
                "issue",
                "view",
                str(number),
                "--repo",
                repository,
                "--json",
                "state,title,url",
            ]
        )
    )
    if item.get("state") == "OPEN":
        run(
            [
                "gh",
                "issue",
                "close",
                str(number),
                "--repo",
                repository,
                "--reason",
                "completed",
            ]
        )
        action = "closed"
    else:
        action = "already-closed"
    return {
        "action": action,
        "repository": repository,
        "number": number,
        "title": str(item.get("title", "")),
        "url": str(item.get("url", "")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if int(plan.get("schema_version", 0)) != 1:
        raise ValueError("unsupported issue plan schema")

    created = [ensure_issue(item) for item in plan.get("issues", [])]
    closed = [close_completed(item) for item in plan.get("close_as_completed", [])]
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "issues": created,
        "closures": closed,
    }

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "issue-application.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        "# Applied refactor issue plan",
        "",
        f"Generated: `{result['generated_at']}`",
        "",
        "## Created or existing issues",
        "",
    ]
    for item in created:
        lines.append(
            f"- **{item['action']}** `{item['repository']}#{item['number']}` — {item['title']}"
        )
    lines.extend(["", "## Closed or already closed", ""])
    for item in closed:
        lines.append(
            f"- **{item['action']}** `{item['repository']}#{item['number']}` — {item['title']}"
        )
    (args.output / "issue-application.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
