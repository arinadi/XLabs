#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# ══════════════════════════════════════════
#  arinanoLabs Bootstrap — curl | bash
#  https://github.com/arinadi/arinanoLabs
# ══════════════════════════════════════════

REPO="https://raw.githubusercontent.com/arinadi/arinanoLabs/main"
ARINANOLABS_DIR="$HOME/.arinanolabs"
SCRIPTS_DIR="${ARINANOLABS_DIR}/scripts"
LAUNCHERS_DIR="${ARINANOLABS_DIR}/launchers"

INSTALLED=false
[ -d "$ARINANOLABS_DIR" ] && INSTALLED=true

# --- Menu (only when interactive) ---
if [ -t 0 ]; then
    echo ""
    echo "╔═══════════════════════════════════════╗"
    echo "║  📱 arinanoX — Linux on Android      ║"
    echo "╠═══════════════════════════════════════╣"

    if $INSTALLED; then
        echo "║  Status: installed                   ║"
        echo "╠═══════════════════════════════════════╣"
        echo "║                                       ║"
        echo "║  [1] Update / Reinstall              ║"
        echo "║  [2] Uninstall                       ║"
        echo "║  [3] Exit                             ║"
        echo "║                                       ║"
    else
        echo "║  Status: not installed                ║"
        echo "╠═══════════════════════════════════════╣"
        echo "║                                       ║"
        echo "║  [1] Install                         ║"
        echo "║  [2] Exit                             ║"
        echo "║                                       ║"
    fi
    echo "╚═══════════════════════════════════════╝"
    echo ""

    read -rp "  Choose: " CHOICE

    if $INSTALLED; then
        case "$CHOICE" in
            1) ACTION="reinstall" ;;
            2) ACTION="uninstall" ;;
            *) echo ">>> Bye!"; exit 0 ;;
        esac
    else
        case "$CHOICE" in
            1) ACTION="install" ;;
            *) echo ">>> Bye!"; exit 0 ;;
        esac
    fi
else
    echo ">>> Installing arinanoX..."
    ACTION="reinstall"
fi

# --- Uninstall ---
if [ "$ACTION" = "uninstall" ]; then
    curl -sL --retry 2 "${REPO}/uninstall.sh" | bash
    exit 0
fi

# --- Install / Reinstall ---
echo ">>> Downloading scripts..."
rm -rf "$SCRIPTS_DIR" "$LAUNCHERS_DIR"
mkdir -p "$SCRIPTS_DIR" "$LAUNCHERS_DIR"

for f in host-setup.sh \
         launcher-gen.sh motd-setup.sh \
         patch.sh \
         seccomp-check.sh seccomp-fix.sh doctor.sh \
         manifest-generate.sh manifest-apply.sh user-snapshot.sh; do
    curl -sL --retry 2 "${REPO}/scripts/${f}" -o "${SCRIPTS_DIR}/${f}"
    chmod +x "${SCRIPTS_DIR}/${f}"
done

# --- Execute Setup ---
echo ">>> Running host setup..."
bash "${SCRIPTS_DIR}/host-setup.sh"

echo ">>> Installing launchers..."
bash "${SCRIPTS_DIR}/launcher-gen.sh"

echo ">>> Setting up MOTD..."
bash "${SCRIPTS_DIR}/motd-setup.sh"

echo ""
echo "╔═══════════════════════════════════════╗"
echo "║  ✅ arinanoLabs ready!                ║"
echo "╠═══════════════════════════════════════╣"
echo "║                                       ║"
echo "║  TUI:  alabs                          ║"
echo "║                                       ║"
echo "╚═══════════════════════════════════════╝"
