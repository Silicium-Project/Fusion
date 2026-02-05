#!/usr/bin/env python3
"""Validate that text files are valid UTF-8."""
from __future__ import annotations

import argparse
import codecs
import os
from pathlib import Path
from typing import Iterable, List, Tuple

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".pytest_cache",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "out",
    "run_output",
    "run_build",
    ".worker_tmp",
}

DEFAULT_EXCLUDE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".7z",
    ".rar",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".wav",
    ".flac",
    ".so",
    ".a",
    ".o",
    ".obj",
    ".exe",
    ".dll",
    ".bin",
    ".dat",
    ".pyc",
    ".class",
    ".jar",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}


def iter_files(root: Path,
               exclude_dirs: Iterable[str],
               exclude_exts: Iterable[str]) -> Iterable[Path]:
    exclude_dirs_set = set(exclude_dirs)
    exclude_exts_set = set(exclude_exts)
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in exclude_dirs_set]
        for name in files:
            path = Path(base) / name
            if path.suffix.lower() in exclude_exts_set:
                continue
            yield path


def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
        return b"\x00" in chunk
    except OSError:
        return False


def is_utf8(path: Path) -> Tuple[bool, str]:
    try:
        decoder = codecs.getincrementaldecoder("utf-8")()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                decoder.decode(chunk)
        decoder.decode(b"", final=True)
        return True, ""
    except UnicodeDecodeError as exc:
        return False, f"{exc}"
    except OSError as exc:
        return False, f"{exc}"


def check_utf8(root: Path,
               exclude_dirs: Iterable[str] = DEFAULT_EXCLUDE_DIRS,
               exclude_exts: Iterable[str] = DEFAULT_EXCLUDE_EXTS) -> List[str]:
    failures: List[str] = []
    for path in iter_files(root, exclude_dirs, exclude_exts):
        if is_binary(path):
            continue
        ok, reason = is_utf8(path)
        if not ok:
            failures.append(f"{path}: {reason}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Check repository files for UTF-8 encoding.")
    parser.add_argument("root", nargs="?", default=".", help="Root directory to scan.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    failures = check_utf8(root)
    if failures:
        print("Non-UTF-8 files detected:")
        for item in failures:
            print(f"- {item}")
        return 1
    print("All checked files are valid UTF-8.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
