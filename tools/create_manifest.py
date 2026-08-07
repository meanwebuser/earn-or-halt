#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--artifact-uri", required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    artifact = args.artifact.resolve()
    if not artifact.is_file():
        raise SystemExit(f"artifact not found: {artifact}")
    with tempfile.TemporaryDirectory(prefix="eoh-sign-") as temporary:
        signature_path = Path(temporary) / "signature.der"
        subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-sign",
                str(args.private_key),
                "-out",
                str(signature_path),
                str(artifact),
            ],
            check=True,
        )
        signature = base64.b64encode(signature_path.read_bytes()).decode("ascii")

    manifest = {
        "schema": "earn-or-halt.release.v1",
        "version": args.version,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact": args.artifact_uri,
        "sha256": sha256_file(artifact),
        "signature": signature,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
