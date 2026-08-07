#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .fetch_resource import fetch_uri
except ImportError:
    from fetch_resource import fetch_uri


ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _load_http_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "EarnOrHalt-Bootstrap/0.1", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Blockscout response is too large")
    return json.loads(raw.decode("utf-8"))


def _decode_input(raw_input: str) -> str:
    value = raw_input.strip()
    if value.startswith("0x"):
        value = value[2:]
    if not value or len(value) % 2:
        raise ValueError("transaction input is not valid hex")
    return bytes.fromhex(value).decode("utf-8").strip().strip("\x00")


def _transaction_sort_key(transaction: dict[str, Any]) -> tuple[str, int, int]:
    timestamp = str(transaction.get("timestamp") or "")
    block = int(transaction.get("block_number") or 0)
    index = int(transaction.get("position") or transaction.get("transaction_index") or 0)
    return timestamp, block, index


def _blockscout_pointer() -> str:
    base = os.getenv("EOH_BLOCKSCOUT_BASE", "https://eth.blockscout.com").rstrip("/")
    addresses = [item.strip() for item in os.getenv("EOH_VANITY_ADDRESSES", "").split(",") if item.strip()]
    if not addresses:
        raise ValueError("EOH_VANITY_ADDRESSES is required for the Blockscout pointer source")
    candidates: list[tuple[tuple[str, int, int], str]] = []
    errors: list[str] = []
    for address in addresses:
        if not ADDRESS_RE.fullmatch(address):
            errors.append(f"invalid address: {address}")
            continue
        endpoint = f"{base}/api/v2/addresses/{address}/transactions"
        try:
            value = _load_http_json(endpoint)
            items = value.get("items", []) if isinstance(value, dict) else []
            for transaction in items:
                if not isinstance(transaction, dict):
                    continue
                destination = transaction.get("to")
                if isinstance(destination, dict):
                    destination = destination.get("hash")
                if destination and str(destination).lower() != address.lower():
                    continue
                raw_input = transaction.get("raw_input") or transaction.get("input")
                if not isinstance(raw_input, str) or raw_input in {"", "0x"}:
                    continue
                try:
                    decoded = _decode_input(raw_input)
                except Exception:
                    continue
                candidates.append((_transaction_sort_key(transaction), decoded))
        except Exception as error:
            errors.append(f"{address}: {error}")
    if not candidates:
        raise RuntimeError("no usable pointer transaction found; " + "; ".join(errors))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _validate_manifest(path: Path) -> None:
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise ValueError("release manifest must be a JSON object")
    required = {"schema", "version", "artifact", "sha256", "signature"}
    missing = sorted(required.difference(manifest))
    if missing:
        raise ValueError("release manifest is missing: " + ", ".join(missing))
    if manifest["schema"] != "earn-or-halt.release.v1":
        raise ValueError("unsupported release manifest schema")


def resolve(output: Path) -> None:
    source = os.getenv("EOH_POINTER_SOURCE", "file").strip().lower()
    if source == "file":
        pointer = os.getenv("EOH_POINTER_FILE", "./manifest.json")
        uri = Path(pointer).expanduser().resolve().as_uri()
        fetch_uri(uri, output, 4 * 1024 * 1024)
    elif source == "url":
        uri = os.getenv("EOH_POINTER_URL", "").strip()
        if not uri:
            raise ValueError("EOH_POINTER_URL is required")
        fetch_uri(uri, output, 4 * 1024 * 1024)
    elif source == "blockscout":
        pointer = _blockscout_pointer()
        if pointer.startswith("{"):
            output.write_text(pointer, encoding="utf-8")
        else:
            parsed = urllib.parse.urlparse(pointer)
            if parsed.scheme not in {"https", "http", "ipfs", "ipns", "file"}:
                raise ValueError("transaction input must contain a manifest JSON object or supported URI")
            fetch_uri(pointer, output, 4 * 1024 * 1024)
    else:
        raise ValueError("EOH_POINTER_SOURCE must be file, url, or blockscout")
    _validate_manifest(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    resolve(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
