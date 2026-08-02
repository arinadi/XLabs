#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  arinanoLabs TUI Test Script (Podman)
#  Usage: bash test-tui.sh
# ═══════════════════════════════════════════════════════════════
set -e

IMAGE="arinanolabs-dev"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ">>> Building container image..."
podman build -t "$IMAGE" -f docker/dev/Dockerfile docker/dev

echo ""
echo ">>> Starting TUI test container..."
echo "    (Project mounted at /data/data/com.termux/files/home/arinanoLabs)"
echo ""

podman run -it --rm \
    -v "${PROJECT_DIR}:/data/data/com.termux/files/home/arinanoLabs" \
    "$IMAGE" bash -c "
        cd /data/data/com.termux/files/home/arinanoLabs
        pip install rich requests --quiet 2>/dev/null || true
        python install.py
    "
