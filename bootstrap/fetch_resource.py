#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import urllib.parse
import urllib.request
import queue
import threading
from pathlib import Path


DEFAULT_GATEWAYS = "https://ipfs.io,https://dweb.link"


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _copy_limited(response, destination: Path, maximum_bytes: int) -> None:
    total = 0
    with destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError(f"resource exceeds {maximum_bytes} bytes")
            handle.write(chunk)


def _download_http(url: str, destination: Path, maximum_bytes: int) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"https", "http"}:
        raise ValueError("unsupported HTTP scheme")
    if parsed.scheme == "http" and not _bool_env("EOH_ALLOW_HTTP", False):
        raise ValueError("plain HTTP is disabled; set EOH_ALLOW_HTTP=1 only for a trusted local registry")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "EarnOrHalt-Bootstrap/0.1", "Accept": "*/*"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        _copy_limited(response, destination, maximum_bytes)


def _gateway_urls(uri: str) -> list[str]:
    parsed = urllib.parse.urlparse(uri)
    kind = parsed.scheme
    root = parsed.netloc
    path = parsed.path.lstrip("/")
    if not root:
        raise ValueError(f"{kind} URI has no name/CID")
    gateways = [
        value.strip().rstrip("/")
        for value in os.getenv("EOH_IPFS_GATEWAYS", DEFAULT_GATEWAYS).split(",")
        if value.strip()
    ]
    suffix = f"/{path}" if path else ""
    return [f"{gateway}/{kind}/{root}{suffix}" for gateway in gateways]


def _download_worker(url: str, temporary: Path, maximum_bytes: int, results: queue.Queue) -> None:
    try:
        _download_http(url, temporary, maximum_bytes)
        results.put((url, temporary, None))
    except Exception as error:
        temporary.unlink(missing_ok=True)
        results.put((url, None, str(error)))


def _race_http(urls: list[str], output: Path, maximum_bytes: int) -> None:
    if not urls:
        raise ValueError("no IPFS gateways configured")
    output.parent.mkdir(parents=True, exist_ok=True)
    results: queue.Queue = queue.Queue()
    temporary_paths: list[Path] = []
    errors: list[str] = []
    for url in urls:
        fd, name = tempfile.mkstemp(prefix=".eoh-fetch-", dir=str(output.parent))
        os.close(fd)
        temporary = Path(name)
        temporary_paths.append(temporary)
        threading.Thread(
            target=_download_worker,
            args=(url, temporary, maximum_bytes, results),
            daemon=True,
            name="eoh-gateway-fetch",
        ).start()
    try:
        for _ in urls:
            url, temporary, error = results.get(timeout=25)
            if temporary:
                os.replace(temporary, output)
                return
            errors.append(f"{url}: {error}")
        raise RuntimeError("all resource gateways failed: " + "; ".join(errors))
    finally:
        for temporary in temporary_paths:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def fetch_uri(uri: str, output: Path, maximum_bytes: int) -> None:
    parsed = urllib.parse.urlparse(uri)
    output.parent.mkdir(parents=True, exist_ok=True)
    if parsed.scheme == "file":
        if not _bool_env("EOH_ALLOW_FILE_URI", True):
            raise ValueError("file:// resources are disabled")
        source = Path(urllib.request.url2pathname(parsed.path)).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.stat().st_size > maximum_bytes:
            raise ValueError(f"resource exceeds {maximum_bytes} bytes")
        shutil.copyfile(source, output)
        return
    if parsed.scheme in {"https", "http"}:
        _download_http(uri, output, maximum_bytes)
        return
    if parsed.scheme in {"ipfs", "ipns"}:
        _race_http(_gateway_urls(uri), output, maximum_bytes)
        return
    raise ValueError(f"unsupported resource URI scheme: {parsed.scheme or '(none)'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("uri")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=int(os.getenv("EOH_FETCH_MAX_BYTES", str(256 * 1024 * 1024))),
    )
    args = parser.parse_args()
    fetch_uri(args.uri, args.output, args.max_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
