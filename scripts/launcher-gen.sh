#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

echo ">>> Setting up arinanoLabs..."

# Remove old v1 shortcuts
rm -f ~/.shortcuts/{start,stop,update}{,-x11,-xfce,-arinanox,-proot}.sh 2>/dev/null || true
rm -f ~/.shortcuts/kill-{x11,proot,all}.sh 2>/dev/null || true
rm -f ~/.shortcuts/0-stop-*.sh ~/.shortcuts/1-start-*.sh ~/.shortcuts/2-update-*.sh 2>/dev/null || true
rm -f ~/{start,stop,update}{,-x11,-xfce,-arinanox}.sh 2>/dev/null || true
rm -f ~/kill-{x11,proot,all}.sh 2>/dev/null || true

echo ">>> Done. Use 'alabs' to launch TUI."
