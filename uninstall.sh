#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# uninstall.sh — Clean uninstall of arinanoLabs
# Removes: proot container, generated scripts, configs

echo "╔═══════════════════════════════════╗"
echo "║  🗑️  arinanoLabs Uninstaller      ║"
echo "╠═══════════════════════════════════╣"
echo ""
echo "This will remove:"
echo "  • proot container (arinanolabs)"
echo "  • ~/.local/bin/alabs"
echo "  • ~/.arinanolabs/ cache"
echo ""
echo "This will NOT remove:"
echo "  • ~/arinanoLabs/ (git repo)"
echo "  • ~/storage/ (Android storage)"
echo "  • ~/.bashrc (Termux config)"
echo ""

if [ -t 0 ]; then read -rp "Proceed? [y/N] " confirm; else confirm="y"; fi
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""

# 1. Stop any running sessions
echo ">>> Stopping running sessions..."
pkill -f "mate-session" 2>/dev/null && echo "  [x] MATE stopped" || true
pkill -f "proot-distro login" 2>/dev/null && echo "  [x] proot login stopped" || true
pkill -f "termux-x11" 2>/dev/null && echo "  [x] X11 stopped" || true
pulseaudio --kill 2>/dev/null && echo "  [x] PulseAudio stopped" || true
termux-wake-unlock 2>/dev/null && echo "  [x] Wake lock released" || true
sleep 1

# 2. Remove proot container
echo ""
echo ">>> Removing proot container..."
if proot-distro list 2>/dev/null | grep -q "arinanolabs"; then
    proot-distro remove arinanolabs 2>&1 && echo "  [x] arinanolabs removed" || echo "  [-] Failed to remove"
fi

# 3. Remove alabs launcher
echo ""
echo ">>> Removing alabs launcher..."
rm -f ~/.local/bin/alabs
echo "  [x] ~/.local/bin/alabs removed"

# 4. Remove ~/.arinanolabs cache
echo ""
echo ">>> Removing ~/.arinanolabs cache..."
rm -rf ~/.arinanolabs
echo "  [x] ~/.arinanolabs removed"

# 6. Clean Termux tmp
echo ""
echo ">>> Cleaning Termux tmp..."
TERMUX_TMP="${TMPDIR:-/data/data/com.termux/files/usr/tmp}"
rm -f "${TERMUX_TMP}/.X0-lock" 2>/dev/null
rm -rf "${TERMUX_TMP}/.X11-unix" 2>/dev/null
rm -f "${TERMUX_TMP}/pulse-socket" 2>/dev/null
echo "  [x] Temp files cleaned"

echo ""
echo "╔═══════════════════════════════════╗"
echo "║  ✅ arinanoLabs uninstalled       ║"
echo "╠═══════════════════════════════════╣"
echo "║                                   ║"
echo "║  To reinstall:                    ║"
echo "║  curl -sL URL/install.sh | bash   ║"
echo "║                                   ║"
echo "╚═══════════════════════════════════╝"
