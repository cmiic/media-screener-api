#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/../model.env"

MODEL_FILE="${1:-models/640m.onnx}"

mkdir -p "$(dirname "$MODEL_FILE")"

if [ -f "$MODEL_FILE" ] && echo "$MODEL_SHA256  $MODEL_FILE" | sha256sum --check --strict >/dev/null 2>&1; then
    echo "Model already verified at $MODEL_FILE"
    exit 0
fi

TEMP_FILE=$(mktemp "${MODEL_FILE}.tmp.XXXXXX")
trap 'rm -f "$TEMP_FILE"' EXIT HUP INT TERM

set -- --fail --location --retry 3 --retry-all-errors \
    --header "Accept: application/octet-stream" \
    --header "X-GitHub-Api-Version: 2022-11-28" \
    --output "$TEMP_FILE" \
    "$MODEL_API_URL"
if [ -n "${GITHUB_TOKEN:-}" ]; then
    set -- --header "Authorization: Bearer $GITHUB_TOKEN" "$@"
fi
curl "$@"

echo "$MODEL_SHA256  $TEMP_FILE" | sha256sum --check --strict
chmod 0644 "$TEMP_FILE"
mv "$TEMP_FILE" "$MODEL_FILE"
trap - EXIT HUP INT TERM

echo "Model provisioned at $MODEL_FILE"