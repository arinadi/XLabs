#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  arinanoLabs TUI Test Script (Podman)
#
#  Purpose: Test TUI locally on PC using Podman
#  Usage: bash test-tui.sh
#
#  NOTE: This is for LOCAL TESTING ONLY.
#        Actual install happens on Android (Termux).
#
#  What this tests:
#    - TUI welcome screen
#    - Pre-flight checks
#    - Menu navigation
#    - GPU detection
#
#  What this does NOT test:
#    - Actual desktop launch (no X11 in container)
#    - proot-distro (not available in container)
#    - Termux packages (pkg not available)
# ═══════════════════════════════════════════════════════════════
set -e

IMAGE="arinanolabs-dev"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "═══════════════════════════════════════════"
echo "  arinanoLabs TUI Test (Podman)"
echo "═══════════════════════════════════════════"
echo ""

# Check Podman
if ! command -v podman &>/dev/null; then
    echo "✗ Podman not found. Install: https://podman-desktop.io/"
    exit 1
fi

# Check Podman machine
if ! podman machine info &>/dev/null; then
    echo ">>> Starting Podman machine..."
    podman machine init 2>/dev/null || true
    podman machine start
fi

echo ">>> Building dev container..."
podman build -t "$IMAGE" -f docker/dev/Dockerfile docker/dev 2>&1 | tail -5

echo ""
echo ">>> Running TUI test..."
echo "    (Project mounted at /data/data/com.termux/files/home/arinanoLabs)"
echo "    Press Ctrl+C to exit"
echo ""

podman run -it --rm \
    -v "${PROJECT_DIR}:/data/data/com.termux/files/home/arinanoLabs" \
    "$IMAGE" bash -c "
        cd /data/data/com.termux/files/home/arinanoLabs
        pip install rich requests --quiet 2>/dev/null || true
        python install.py
    "
