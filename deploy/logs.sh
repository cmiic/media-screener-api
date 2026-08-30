#!/bin/bash
# Follow logs from the standalone media screener container.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

CONTAINER_NAME="${CONTAINER_NAME:-media-screener}"

$RUNTIME logs -f "$CONTAINER_NAME"
