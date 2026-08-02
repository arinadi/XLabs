#!/data/data/com.termux/files/usr/bin/bash
# ═══════════════════════════════════════════════════════════════
# arinanoX — Manifest Apply
# Reads user-manifest.yaml, installs packages, restores dotfiles
# Called automatically after `arinanox update`
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

MANIFEST="$HOME/.arinanox/user-manifest.yaml"
ROOTFS="/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanox/rootfs"
BACKUP_DIR="/sdcard/arinanox-backup"

if [ ! -f "$MANIFEST" ]; then
    echo "  • No user-manifest.yaml — skipping user layer"
    exit 0
fi

echo ">>> Applying user manifest..."

# ── Install packages ────────────────────────────────────────
if grep -q "^packages:" "$MANIFEST" 2>/dev/null; then
    PKGS=$(sed -n '/^packages:/,/^[a-z]/p' "$MANIFEST" | grep -E "^\s+- " | sed 's/^\s*- //' | grep -v "^#" | tr '\n' ' ')
    PKGS=$(echo "$PKGS" | xargs)  # trim
    
    if [ -n "$PKGS" ]; then
        echo "  Installing: $PKGS"
        proot-distro login arinanox -- bash -c "
            sudo apt-get update -qq 2>/dev/null
            for pkg in $PKGS; do
                echo \"    → \$pkg\"
                sudo apt-get install -y -qq \"\$pkg\" 2>/dev/null || echo \"    ⚠ skipped: \$pkg\"
            done
        " || true
        echo "  ✓ Packages installed"
    else
        echo "  • No packages in manifest"
    fi
fi

# ── Restore dotfiles from backup ────────────────────────────
if [ -d "$BACKUP_DIR/home" ]; then
    echo "  Restoring dotfiles from backup..."
    for df in .bashrc .bash_aliases .gitconfig; do
        src="$BACKUP_DIR/home/$df"
        dest="$ROOTFS/home/admin/$df"
        if [ -f "$src" ]; then
            mkdir -p "$(dirname "$dest")"
            cp "$src" "$dest"
            echo "    → $df"
        fi
    done
    echo "  ✓ Dotfiles restored"
else
    echo "  • No backup found — skipping dotfiles"
fi

echo ""
echo "  ✓ User manifest applied."
echo "  Start: arinanox start"
