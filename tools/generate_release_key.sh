#!/bin/sh
set -eu

OUT_DIR=${1:-.release-keys}
mkdir -p "$OUT_DIR"
PRIVATE="$OUT_DIR/release-private.pem"
PUBLIC="$OUT_DIR/release-public.pem"

[ ! -e "$PRIVATE" ] || { echo "refusing to overwrite $PRIVATE" >&2; exit 1; }
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:secp256k1 -out "$PRIVATE"
chmod 600 "$PRIVATE"
openssl pkey -in "$PRIVATE" -pubout -out "$PUBLIC"
chmod 644 "$PUBLIC"
printf 'private: %s\npublic:  %s\n' "$PRIVATE" "$PUBLIC"
