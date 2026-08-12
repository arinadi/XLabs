#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# uninstall.sh — Clean uninstall of XLabs
# Removes: proot container, generated scripts, configs

echo "╔═══════════════════════════════════╗"
echo "║  🗑️  XLabs Uninstaller      ║"
echo "╠═══════════════════════════════════╣"
echo ""
echo "This will remove:"
echo "  • proot container (xlabs)"
echo "  • ~/bin/xlabs launcher"
echo "  • ~/XLabs (git repo)"
echo ""
echo "This will NOT remove:"
echo "  • ~/storage/ (Android storage)"
echo "  • ~/.bashrc (Termux config)"
echo ""

if [ -t 0 ]; then read -rp "Proceed? [y/N] " confirm; else confirm="y"; fi
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""

# 1. Stop any running sessions.
# Reuse the TUI's teardown rather than keeping a second, subtly different
# copy of it here — that copy killed every "proot-distro login" on the
# device, not just this container's.
echo ">>> Stopping running sessions..."
REPO_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
if [ -f "$REPO_DIR/installer/start.py" ] && command -v python3 >/dev/null 2>&1; then
    PYTHONPATH="$REPO_DIR" python3 -c \
        'from installer.start import stop_desktop; stop_desktop(print)' \
        || echo "  [-] stop reported a problem, continuing"
else
    echo "  [-] repo or python3 missing, falling back to a scoped kill"
    pkill -f "proot.*xlabs" 2>/dev/null && echo "  [x] container stopped" || true
    pkill -f "termux-x11" 2>/dev/null && echo "  [x] X11 stopped" || true
    pulseaudio --kill 2>/dev/null && echo "  [x] PulseAudio stopped" || true
    termux-wake-unlock 2>/dev/null || true
fi
sleep 1

# 2. Remove proot container
echo ""
echo ">>> Removing proot container..."
if proot-distro list 2>/dev/null | grep -q "xlabs"; then
    proot-distro remove xlabs 2>&1 && echo "  [x] xlabs removed" || echo "  [-] Failed to remove"
fi

# 3. Remove xlabs launcher
echo ""
echo ">>> Removing xlabs launcher..."
rm -f ~/bin/xlabs
echo "  [x] ~/bin/xlabs removed"

# 4. Remove git repo
echo ""
echo ">>> Removing ~/XLabs..."
rm -rf ~/XLabs
echo "  [x] ~/XLabs removed"

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
echo "║  ✅ XLabs uninstalled       ║"
echo "╠═══════════════════════════════════╣"
echo "║                                   ║"
echo "║  To reinstall:                    ║"
echo "║  curl -sL URL/install.sh | bash   ║"
echo "║                                   ║"
echo "╚═══════════════════════════════════╝"
