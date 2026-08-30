#!/bin/bash
# Start the media screener for a standalone local run, with hardening.
#
# The host port binds to loopback by default. This screener has no built-in
# authentication and must not be published to an untrusted network.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment variables
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
fi

# Detect available container runtime
if command -v podman &> /dev/null; then
    RUNTIME="podman"
elif command -v docker &> /dev/null; then
    RUNTIME="docker"
else
    echo "Error: No container runtime found. Install podman or docker."
    exit 1
fi

IMAGE_NAME="${IMAGE_NAME:-media-screener}"
CONTAINER_NAME="${CONTAINER_NAME:-media-screener}"
HOST_PORT="${HOST_PORT:-8080}"
HOST_IP="${HOST_IP:-127.0.0.1}"
MEMORY_LIMIT="${MEMORY_LIMIT:-2g}"
CPU_LIMIT="${CPU_LIMIT:-2}"
MAX_UPLOAD_SIZE="${MAX_UPLOAD_SIZE:-209715200}"
MAX_PDF_PAGES="${MAX_PDF_PAGES:-100}"
MAX_PDF_RENDERED_PIXELS="${MAX_PDF_RENDERED_PIXELS:-100000000}"
MAX_VIDEO_DURATION_SECONDS="${MAX_VIDEO_DURATION_SECONDS:-600}"
MAX_VIDEO_SAMPLED_FRAMES="${MAX_VIDEO_SAMPLED_FRAMES:-120}"
MAX_DOCUMENT_IMAGES="${MAX_DOCUMENT_IMAGES:-100}"
MAX_CONCURRENT_SCANS="${MAX_CONCURRENT_SCANS:-1}"
SCAN_QUEUE_TIMEOUT_SECONDS="${SCAN_QUEUE_TIMEOUT_SECONDS:-5}"
UPLOAD_TIMEOUT_SECONDS="${UPLOAD_TIMEOUT_SECONDS:-10}"
PROCESSING_TIMEOUT_SECONDS="${PROCESSING_TIMEOUT_SECONDS:-40}"
MODEL_FILE="${MODEL_FILE:-$PROJECT_DIR/models/640m.onnx}"
. "$PROJECT_DIR/model.env"

if [ ! -f "$MODEL_FILE" ]; then
    echo "Error: Model not found at $MODEL_FILE" >&2
    echo "Run: $PROJECT_DIR/scripts/provision-model.sh \"$MODEL_FILE\"" >&2
    exit 1
fi

echo "$MODEL_SHA256  $MODEL_FILE" | sha256sum --check --strict

# Stop existing container if running
if $RUNTIME container exists "$CONTAINER_NAME" 2>/dev/null || $RUNTIME ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping existing container..."
    $RUNTIME stop "$CONTAINER_NAME" 2>/dev/null || true
    $RUNTIME rm "$CONTAINER_NAME" 2>/dev/null || true
fi

echo "Starting $CONTAINER_NAME using $RUNTIME..."
echo "  Listening on: $HOST_IP:$HOST_PORT"
echo "  Memory limit: $MEMORY_LIMIT"
echo "  CPU limit: $CPU_LIMIT"

$RUNTIME run -d \
    --restart=always \
    --name "$CONTAINER_NAME" \
    -p "$HOST_IP:$HOST_PORT:8080" \
    --memory="$MEMORY_LIMIT" \
    --cpus="$CPU_LIMIT" \
    --read-only \
    --tmpfs /tmp:size=512m \
    --volume "$MODEL_FILE:/models/640m.onnx:ro" \
    --env MAX_UPLOAD_SIZE="$MAX_UPLOAD_SIZE" \
    --env MAX_PDF_PAGES="$MAX_PDF_PAGES" \
    --env MAX_PDF_RENDERED_PIXELS="$MAX_PDF_RENDERED_PIXELS" \
    --env MAX_VIDEO_DURATION_SECONDS="$MAX_VIDEO_DURATION_SECONDS" \
    --env MAX_VIDEO_SAMPLED_FRAMES="$MAX_VIDEO_SAMPLED_FRAMES" \
    --env MAX_DOCUMENT_IMAGES="$MAX_DOCUMENT_IMAGES" \
    --env MAX_CONCURRENT_SCANS="$MAX_CONCURRENT_SCANS" \
    --env SCAN_QUEUE_TIMEOUT_SECONDS="$SCAN_QUEUE_TIMEOUT_SECONDS" \
    --env UPLOAD_TIMEOUT_SECONDS="$UPLOAD_TIMEOUT_SECONDS" \
    --env PROCESSING_TIMEOUT_SECONDS="$PROCESSING_TIMEOUT_SECONDS" \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    "$IMAGE_NAME"

echo "Done. Container: $CONTAINER_NAME"
echo "API available at: http://$HOST_IP:$HOST_PORT"
echo "Docs available at: http://$HOST_IP:$HOST_PORT/docs"
