#!/bin/bash
# Stop and remove the standalone media screener container.

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

if $RUNTIME container exists "$CONTAINER_NAME" 2>/dev/null || $RUNTIME ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping $CONTAINER_NAME..."
    $RUNTIME stop "$CONTAINER_NAME"
    $RUNTIME rm "$CONTAINER_NAME"
    echo "Done."
else
    echo "Container $CONTAINER_NAME not found."
fi
