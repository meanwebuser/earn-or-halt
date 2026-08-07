#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEMO_DIR=${EOH_DEMO_DIR:-"$ROOT/.demo"}
PORT=${EOH_DEMO_PORT:-18787}
rm -rf "$DEMO_DIR"
mkdir -p "$DEMO_DIR"

"$ROOT/tools/generate_release_key.sh" "$DEMO_DIR/keys"
python3 "$ROOT/tools/build_release.py" --root "$ROOT" --output "$DEMO_DIR/release.tar.gz" >/dev/null
ARTIFACT_URI=$(python3 - "$DEMO_DIR/release.tar.gz" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve().as_uri())
PY
)
python3 "$ROOT/tools/create_manifest.py" \
    --artifact "$DEMO_DIR/release.tar.gz" \
    --artifact-uri "$ARTIFACT_URI" \
    --private-key "$DEMO_DIR/keys/release-private.pem" \
    --version 0.1.0-demo \
    --output "$DEMO_DIR/manifest.json" >/dev/null

EOH_POINTER_SOURCE=file \
EOH_POINTER_FILE="$DEMO_DIR/manifest.json" \
EOH_RELEASE_PUBKEY="$DEMO_DIR/keys/release-public.pem" \
EOH_INSTALL_ROOT="$DEMO_DIR/install" \
EOH_DATA_DIR="$DEMO_DIR/data" \
EOH_PID_FILE="$DEMO_DIR/earn-or-halt.pid" \
EOH_LOG_FILE="$DEMO_DIR/earn-or-halt.log" \
EOH_PORT="$PORT" \
EOH_PROVIDER=mock \
EOH_FOREGROUND=0 \
"$ROOT/bootstrap.sh"

python3 - "$PORT" <<'PY'
import json
import sys
import time
import urllib.request

port = int(sys.argv[1])
health = f"http://127.0.0.1:{port}/healthz"
for _ in range(100):
    try:
        with urllib.request.urlopen(health, timeout=0.5) as response:
            if response.status == 200:
                break
    except Exception:
        time.sleep(0.1)
else:
    raise SystemExit("service did not become healthy")

body = json.dumps({
    "recipient_name": "Анна",
    "recipient_title": "директор по развитию",
    "company": "Example Industrial",
    "icp": "региональное производство",
    "offer": "автоматизировать обработку входящих заявок с помощью ИИ",
    "tone": "коротко и по делу",
    "price_cents": 29,
    "wait_seconds": 10,
}).encode("utf-8")
request = urllib.request.Request(
    f"http://127.0.0.1:{port}/v1/generate",
    data=body,
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=15) as response:
    result = json.loads(response.read().decode("utf-8"))
print(json.dumps(result, ensure_ascii=False, indent=2))
PY

PID=$(cat "$DEMO_DIR/earn-or-halt.pid")
echo
echo "Earn or Halt demo is running."
echo "API:  http://127.0.0.1:$PORT"
echo "PID:  $PID"
echo "Log:  $DEMO_DIR/earn-or-halt.log"
echo "Stop: kill $PID"
