#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import os
import tarfile
from pathlib import Path


DEFAULT_ENTRIES = [
    "earn_or_halt",
    "README.md",
    "LICENSE",
    "pyproject.toml",
    ".env.example",
]


def _iter_files(root: Path, entries: list[str]):
    for entry in entries:
        path = root / entry
        if not path.exists():
            continue
        if path.is_file():
            yield path
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file() and "__pycache__" not in child.parts and child.suffix != ".pyc":
                yield child


def build(root: Path, output: Path, entries: list[str]) -> None:
    root = root.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in _iter_files(root, entries):
                    relative = path.relative_to(root).as_posix()
                    info = archive.gettarinfo(str(path), arcname=relative)
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    info.mtime = 0
                    info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
                    with path.open("rb") as handle:
                        archive.addfile(info, handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--entry", action="append", dest="entries")
    args = parser.parse_args()
    build(args.root, args.output, args.entries or DEFAULT_ENTRIES)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
