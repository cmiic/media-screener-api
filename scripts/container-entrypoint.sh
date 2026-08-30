#!/bin/sh

set -eu

MODEL_PATH="${MODEL_PATH:-/models/640m.onnx}"
. /app/model.env

if [ ! -f "$MODEL_PATH" ]; then
    echo "Model not found at $MODEL_PATH. Mount a provisioned 640m.onnx file at that path." >&2
    exit 1
fi

echo "$MODEL_SHA256  $MODEL_PATH" | sha256sum --check --strict

exec "$@"