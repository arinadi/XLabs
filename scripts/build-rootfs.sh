#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Build & push arinanoLabs image to GHCR
#
#  Usage: bash scripts/build-rootfs.sh [--push]
#
#  --push   Also push to ghcr.io/arinadi/arinanolabs
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

IMAGE="arinanolabs:latest"
REGISTRY="ghcr.io/arinadi/arinanolabs"
DO_PUSH="${1:-}"

echo ""
echo "═══════════════════════════════════════════"
echo "  arinanoLabs Image Builder"
echo "═══════════════════════════════════════════"
echo ""

# Check podman/docker
if command -v podman &>/dev/null; then
    RUNTIME="podman"
elif command -v docker &>/dev/null; then
    RUNTIME="docker"
else
    echo "✗ Neither podman nor docker found"
    exit 1
fi

echo "Using runtime: $RUNTIME"

# Build image
echo ""
echo ">>> [1/2] Building image..."
$RUNTIME build -t "$IMAGE" -f image/Dockerfile .

# Tag for registry
echo ""
echo ">>> Tagging for GHCR..."
$RUNTIME tag "$IMAGE" "$REGISTRY:latest"

if [[ "$DO_PUSH" == "--push" ]]; then
    echo ""
    echo ">>> [2/2] Pushing to GHCR..."
    echo "  (Make sure you're logged in: $RUNTIME login ghcr.io)"
    $RUNTIME push "$REGISTRY:latest"
    echo ""
    echo "✅ Pushed to $REGISTRY:latest"
else
    echo ""
    echo ">>> [2/2] Skipping push (use --push to push)"
fi

SIZE=$($RUNTIME image inspect "$IMAGE" --format '{{.Size}}' | awk '{printf "%.1f MB", $1/1024/1024}')
echo ""
echo "╔═══════════════════════════════════════╗"
echo "║  ✅ Image built: $SIZE"
echo "║  $IMAGE"
echo "╚═══════════════════════════════════════╝"
echo ""
echo "Installer will pull from: $REGISTRY:latest"
