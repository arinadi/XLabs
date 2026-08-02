#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
REPO="https://raw.githubusercontent.com/arinadi/arinanoLabs/main"

echo ">>> Updating arinanoLabs..."
curl -sL --retry 2 "${REPO}/install.sh" | bash
