#!/bin/bash
# Build the media screener container image for a standalone local run.

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

echo "Building $IMAGE_NAME using $RUNTIME..."
$RUNTIME build -t "$IMAGE_NAME" "$PROJECT_DIR"

echo "Done. Image: $IMAGE_NAME"
