#!/bin/sh
set -eu

if [ "$#" -lt 4 ]; then
    echo "usage: $0 ARTIFACT PRIVATE_KEY VERSION OUTPUT_MANIFEST [IPNS_KEY_NAME]" >&2
    exit 2
fi

ARTIFACT=$1
PRIVATE_KEY=$2
VERSION=$3
MANIFEST=$4
IPNS_KEY=${5:-}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

command -v ipfs >/dev/null 2>&1 || { echo "Kubo 'ipfs' CLI is required" >&2; exit 1; }
ARTIFACT_CID=$(ipfs add -Q "$ARTIFACT")
python3 "$ROOT/tools/create_manifest.py" \
    --artifact "$ARTIFACT" \
    --artifact-uri "ipfs://$ARTIFACT_CID" \
    --private-key "$PRIVATE_KEY" \
    --version "$VERSION" \
    --output "$MANIFEST"
MANIFEST_CID=$(ipfs add -Q "$MANIFEST")

echo "artifact: ipfs://$ARTIFACT_CID"
echo "manifest: ipfs://$MANIFEST_CID"

if [ -n "$IPNS_KEY" ]; then
    ipfs name publish --key="$IPNS_KEY" "/ipfs/$MANIFEST_CID"
    IPNS_NAME=$(ipfs key list -l | awk -v key="$IPNS_KEY" '$2 == key {print $1; exit}')
    [ -n "$IPNS_NAME" ] || { echo "unable to resolve IPNS key id" >&2; exit 1; }
    echo "pointer: ipns://$IPNS_NAME"
else
    echo "pointer: ipfs://$MANIFEST_CID"
fi
