#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import tarfile
from pathlib import Path, PurePosixPath


def _safe_destination(root: Path, name: str) -> Path:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"unsafe archive path: {name}")
    destination = (root / Path(*pure.parts)).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"archive path escapes destination: {name}") from error
    return destination


def extract(archive: Path, destination: Path, *, max_files: int, max_bytes: int) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    total_files = 0
    total_bytes = 0
    with tarfile.open(archive, "r:*") as tar:
        members = tar.getmembers()
        for member in members:
            total_files += 1
            if total_files > max_files:
                raise ValueError("archive contains too many entries")
            if member.islnk() or member.issym() or member.isdev() or member.isfifo():
                raise ValueError(f"unsupported archive entry type: {member.name}")
            if not (member.isdir() or member.isfile()):
                raise ValueError(f"unsupported archive entry: {member.name}")
            if member.isfile():
                total_bytes += member.size
                if total_bytes > max_bytes:
                    raise ValueError("archive expands beyond the configured size limit")
            _safe_destination(destination, member.name)

        for member in members:
            target = _safe_destination(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                os.chmod(target, 0o755)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise ValueError(f"cannot read archive member: {member.name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            executable = bool(member.mode & 0o111)
            os.chmod(target, 0o755 if executable else 0o644)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--max-files", type=int, default=int(os.getenv("EOH_ARCHIVE_MAX_FILES", "5000")))
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=int(os.getenv("EOH_ARCHIVE_MAX_BYTES", str(512 * 1024 * 1024))),
    )
    args = parser.parse_args()
    extract(args.archive, args.destination, max_files=args.max_files, max_bytes=args.max_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
