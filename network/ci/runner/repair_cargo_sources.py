#!/usr/bin/env python3
"""Delete Cargo registry sources that were extracted incompletely.

A self-hosted runner keeps ~/.cargo between jobs. A full disk, a cleanup that
ran during a build or an interrupted job can leave a crate source directory
with missing or truncated files (seen with aws-lc-sys: "error occurred in
cc-rs" on a missing .S file). Cargo does not notice and reuses it.

For every extracted crate that still has its downloaded `.crate` archive, this
checks that each file of the archive exists with the right size. A broken
directory is deleted so that Cargo extracts it again from the archive. A crate
checked once is marked (`.silicium-verified`, holding the archive mtime) and
skipped on later runs.

Several runners on the machine share ~/.cargo, so the check holds Cargo's own
package-cache locks: it never looks at a crate another job is extracting.

Usage: repair_cargo_sources.py [--cargo-home DIR]   (default: $CARGO_HOME or ~/.cargo)
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import os
import shutil
import tarfile
import time
from pathlib import Path
from typing import Iterator

MARKER = ".silicium-verified"
# Lock files Cargo takes while downloading or extracting crates (flock).
CARGO_LOCKS = (".package-cache", ".package-cache-mutate")
LOCK_TIMEOUT_S = 600


@contextlib.contextmanager
def cargo_package_locks(cargo_home: Path) -> Iterator[None]:
    """Hold Cargo's package-cache locks exclusively (waits up to LOCK_TIMEOUT_S)."""
    with contextlib.ExitStack() as stack:
        for name in CARGO_LOCKS:
            handle = stack.enter_context(open(cargo_home / name, "a+b"))
            deadline = time.monotonic() + LOCK_TIMEOUT_S
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"cargo_lock_timeout:{name}") from None
                    time.sleep(2)
        yield


def crate_is_complete(archive: Path, source: Path) -> bool:
    """True when every regular file of `archive` exists in `source` with its size."""
    prefix = source.name + "/"
    with tarfile.open(archive, "r:gz") as crate:
        for member in crate:
            if not member.isfile() or not member.name.startswith(prefix):
                continue
            extracted = source / member.name[len(prefix):]
            try:
                if extracted.stat().st_size != member.size:
                    return False
            except FileNotFoundError:
                return False
    return True


def check_source(source: Path, archive: Path) -> bool:
    """Check one extracted crate; return False (and delete it) when broken."""
    marker = source / MARKER
    stamp = str(archive.stat().st_mtime_ns)
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == stamp:
        return True
    try:
        complete = crate_is_complete(archive, source)
    except (OSError, tarfile.TarError, EOFError):
        # A damaged archive cannot rebuild the sources: drop both, Cargo downloads again.
        archive.unlink(missing_ok=True)
        complete = False
    if not complete:
        print(f"Removing incomplete Cargo source: {source.name}")  # i18n:ignore -- CI log
        shutil.rmtree(source, ignore_errors=True)
        return False
    marker.write_text(stamp, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cargo-home", default=os.environ.get("CARGO_HOME") or str(Path.home() / ".cargo"))
    cargo_home = Path(parser.parse_args().cargo_home)
    registry = cargo_home / "registry"
    if not (registry / "src").is_dir():
        print("No Cargo registry sources yet.")  # i18n:ignore -- CI log
        return 0
    removed = 0
    with cargo_package_locks(cargo_home):
        for index in sorted((registry / "src").glob("*")):
            archives = registry / "cache" / index.name
            for source in sorted(path for path in index.iterdir() if path.is_dir()):
                archive = archives / f"{source.name}.crate"
                if archive.is_file() and not check_source(source, archive):
                    removed += 1
    print(f"Cargo sources checked; {removed} incomplete source(s) removed.")  # i18n:ignore -- CI log
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
