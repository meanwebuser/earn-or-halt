#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SMOKE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/earn-or-halt-smoke.XXXXXX")
PID=""
cleanup() {
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        wait "$PID" 2>/dev/null || true
    fi
    rm -rf "$SMOKE_DIR"
}
trap cleanup EXIT HUP INT TERM

PORT=$(python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)

"$ROOT/tools/generate_release_key.sh" "$SMOKE_DIR/keys" >/dev/null
python3 "$ROOT/tools/build_release.py" --root "$ROOT" --output "$SMOKE_DIR/release.tar.gz" >/dev/null
ARTIFACT_URI=$(python3 - "$SMOKE_DIR/release.tar.gz" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve().as_uri())
PY
)
python3 "$ROOT/tools/create_manifest.py" \
    --artifact "$SMOKE_DIR/release.tar.gz" \
    --artifact-uri "$ARTIFACT_URI" \
    --private-key "$SMOKE_DIR/keys/release-private.pem" \
    --version 0.1.0-smoke \
    --output "$SMOKE_DIR/manifest.json" >/dev/null

EOH_POINTER_SOURCE=file \
EOH_POINTER_FILE="$SMOKE_DIR/manifest.json" \
EOH_RELEASE_PUBKEY="$SMOKE_DIR/keys/release-public.pem" \
EOH_INSTALL_ROOT="$SMOKE_DIR/install" \
EOH_DATA_DIR="$SMOKE_DIR/data" \
EOH_PID_FILE="$SMOKE_DIR/process.pid" \
EOH_LOG_FILE="$SMOKE_DIR/process.log" \
EOH_PORT="$PORT" \
EOH_PROVIDER=mock \
EOH_STARTING_CREDIT_CENTS=10 \
EOH_GRACE_JOBS=1 \
EOH_MINIMUM_MARGIN_PERCENT=20 \
EOH_FOREGROUND=0 \
"$ROOT/bootstrap.sh" >/dev/null
PID=$(cat "$SMOKE_DIR/process.pid")

python3 - "$PORT" <<'PY'
import json
import sys
import time
import urllib.request

port = int(sys.argv[1])
base = f"http://127.0.0.1:{port}"
for _ in range(100):
    try:
        with urllib.request.urlopen(base + "/healthz", timeout=0.5) as response:
            if response.status == 200:
                break
    except Exception:
        time.sleep(0.1)
else:
    raise SystemExit("health check failed")

body = json.dumps({
    "recipient_name": "Test",
    "company": "Smoke Corp",
    "offer": "test the economic governor",
    "price_cents": 29,
    "estimated_cost_cents": 1,
    "wait_seconds": 10,
}).encode()
request = urllib.request.Request(
    base + "/v1/generate",
    data=body,
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=15) as response:
    job = json.loads(response.read().decode())
assert job["status"] == "succeeded", job
assert len(job["result"]["variants"]) == 3, job

with urllib.request.urlopen(base + "/v1/state", timeout=3) as response:
    state = json.loads(response.read().decode())
assert state["stats"]["revenue_cents"] == 29, state
assert state["stats"]["cost_cents"] == 1, state
assert state["stats"]["profit_cents"] == 28, state

halt = urllib.request.Request(
    base + "/v1/halt",
    data=b'{"reason":"smoke test complete"}',
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(halt, timeout=3) as response:
    assert response.status == 202
PY

for _ in $(seq 1 100); do
    if ! kill -0 "$PID" 2>/dev/null; then
        break
    fi
    sleep 0.1
done
if kill -0 "$PID" 2>/dev/null; then
    echo "process did not halt" >&2
    cat "$SMOKE_DIR/process.log" >&2 || true
    exit 1
fi

python3 - "$SMOKE_DIR/data/runtime-state.json" <<'PY'
import json
import sys
from pathlib import Path
state = json.loads(Path(sys.argv[1]).read_text())
assert state["status"] == "halted", state
PY

# The same signed manifest must be rejected after one byte of artifact tampering.
printf 'tamper' >> "$SMOKE_DIR/release.tar.gz"
if EOH_POINTER_SOURCE=file \
   EOH_POINTER_FILE="$SMOKE_DIR/manifest.json" \
   EOH_RELEASE_PUBKEY="$SMOKE_DIR/keys/release-public.pem" \
   EOH_INSTALL_ROOT="$SMOKE_DIR/tampered-install" \
   EOH_DATA_DIR="$SMOKE_DIR/tampered-data" \
   EOH_FOREGROUND=0 \
   "$ROOT/bootstrap.sh" >/dev/null 2>&1; then
    echo "tampered artifact was accepted" >&2
    exit 1
fi

echo "smoke test passed"
