#!/bin/sh
set -eu

SEED_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BOOTSTRAP_DIR=${EOH_BOOTSTRAP_DIR:-"$SEED_DIR/bootstrap"}
PUBLIC_KEY=${EOH_RELEASE_PUBKEY:-"$SEED_DIR/release-public.pem"}
INSTALL_ROOT=${EOH_INSTALL_ROOT:-/opt/earn-or-halt}
DATA_DIR=${EOH_DATA_DIR:-"$INSTALL_ROOT/data"}
FOREGROUND=${EOH_FOREGROUND:-1}
REMOVE_SELF=${EOH_REMOVE_BOOTSTRAP:-0}
PID_FILE=${EOH_PID_FILE:-"$INSTALL_ROOT/earn-or-halt.pid"}
LOG_FILE=${EOH_LOG_FILE:-"$DATA_DIR/earn-or-halt.log"}

WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/earn-or-halt-bootstrap.XXXXXX")
cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM

fail() {
    echo "[earn-or-halt bootstrap] ERROR: $*" >&2
    exit 1
}

command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v openssl >/dev/null 2>&1 || fail "openssl is required"
[ -f "$PUBLIC_KEY" ] || fail "release public key not found: $PUBLIC_KEY"
[ -f "$BOOTSTRAP_DIR/resolve_pointer.py" ] || fail "bootstrap helpers not found: $BOOTSTRAP_DIR"

MANIFEST="$WORK_DIR/manifest.json"
ARTIFACT="$WORK_DIR/release.tar.gz"
SIGNATURE="$WORK_DIR/release.sig"
STAGING="$WORK_DIR/staging"

PYTHONPATH="$BOOTSTRAP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$BOOTSTRAP_DIR/resolve_pointer.py" "$MANIFEST"

python3 - "$MANIFEST" "$WORK_DIR" <<'PY'
import base64
import json
import re
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
output = Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
version = str(manifest["version"])
if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", version):
    raise SystemExit("invalid release version")
sha256 = str(manifest["sha256"]).lower()
if not re.fullmatch(r"[0-9a-f]{64}", sha256):
    raise SystemExit("invalid release sha256")
artifact = str(manifest["artifact"])
if len(artifact) > 4096:
    raise SystemExit("artifact URI is too long")
try:
    signature = base64.b64decode(str(manifest["signature"]), validate=True)
except Exception as error:
    raise SystemExit(f"invalid base64 release signature: {error}")
(output / "version.txt").write_text(version, encoding="utf-8")
(output / "artifact-uri.txt").write_text(artifact, encoding="utf-8")
(output / "sha256.txt").write_text(sha256, encoding="ascii")
(output / "release.sig").write_bytes(signature)
PY

VERSION=$(cat "$WORK_DIR/version.txt")
ARTIFACT_URI=$(cat "$WORK_DIR/artifact-uri.txt")
EXPECTED_SHA256=$(cat "$WORK_DIR/sha256.txt")

PYTHONPATH="$BOOTSTRAP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$BOOTSTRAP_DIR/fetch_resource.py" "$ARTIFACT_URI" "$ARTIFACT"

ACTUAL_SHA256=$(python3 - "$ARTIFACT" <<'PY'
import hashlib
import sys
from pathlib import Path

value = hashlib.sha256()
with Path(sys.argv[1]).open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        value.update(chunk)
print(value.hexdigest())
PY
)
[ "$EXPECTED_SHA256" = "$ACTUAL_SHA256" ] || fail "artifact SHA-256 mismatch"

openssl dgst -sha256 -verify "$PUBLIC_KEY" -signature "$SIGNATURE" "$ARTIFACT" >/dev/null 2>&1 \
    || fail "release signature verification failed"

echo "[earn-or-halt bootstrap] verified release $VERSION"

if [ "$FOREGROUND" != "1" ] && [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        fail "process $OLD_PID from $PID_FILE is already running"
    fi
fi

mkdir -p "$INSTALL_ROOT/releases" "$DATA_DIR"
RELEASE_SUFFIX=$(printf '%s' "$EXPECTED_SHA256" | cut -c1-12)
RELEASE_DIR="$INSTALL_ROOT/releases/$VERSION-$RELEASE_SUFFIX"
if [ ! -d "$RELEASE_DIR" ]; then
    python3 "$BOOTSTRAP_DIR/safe_extract.py" "$ARTIFACT" "$STAGING"
    [ -f "$STAGING/earn_or_halt/__main__.py" ] || fail "release does not contain earn_or_halt/__main__.py"
    mv "$STAGING" "$RELEASE_DIR"
fi
ln -sfn "$RELEASE_DIR" "$INSTALL_ROOT/current"

export PYTHONPATH="$INSTALL_ROOT/current${PYTHONPATH:+:$PYTHONPATH}"
export EOH_DATA_DIR="$DATA_DIR"
export PYTHONDONTWRITEBYTECODE=1

if [ "$REMOVE_SELF" = "1" ]; then
    rm -f -- "$0" || true
fi

if [ "$FOREGROUND" = "1" ]; then
    cleanup
    trap - EXIT INT HUP TERM
    exec python3 -m earn_or_halt run
fi

mkdir -p "$(dirname -- "$PID_FILE")" "$(dirname -- "$LOG_FILE")"
nohup python3 -m earn_or_halt run >>"$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
echo "[earn-or-halt bootstrap] started PID $PID; log: $LOG_FILE"
exit 0
