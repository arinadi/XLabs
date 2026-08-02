#!/data/data/com.termux/files/usr/bin/bash
# ═══════════════════════════════════════════════════════════════
# arinanoX — Manifest Generator
# Scans user state, generates ~/arinanoLabs/user-manifest.yaml
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

MANIFEST="$HOME/arinanoLabs/user-manifest.yaml"
ROOTFS="/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/rootfs"

echo ">>> Generating user-manifest.yaml..."

# ── Detect user-added APT packages ──────────────────────────
# Compare apt-mark showmanual against base image packages
BASE_PKGS="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/arinanolabs-base-pkgs.txt"
USER_PKGS="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/arinanolabs-user-pkgs.txt"

# Get all manually-installed packages
proot-distro login arinanolabs -- bash -c 'apt-mark showmanual 2>/dev/null | sort' > "$USER_PKGS" 2>/dev/null || true

# Get base packages from fresh image (from Dockerfile-like list)
# For now: list known core packages and exclude them
cat > "$BASE_PKGS" <<'BASE'
adduser
apt
bash
busybox
ca-certificates
curl
dbus
dbus-x11
firefox-esr
gcc
git
glmark2
gnupg
htop
make
mesa-utils
mate-desktop-environment
mate-terminal
mate-system-monitor
mate-utils
mate-applets
mate-media
mate-netbook
mate-panel
mate-screensaver
mate-session-manager
mate-polkit
mate-power-manager
mate-disk-utility-utils
pluma
eom
atril
engrampa
marco
network-manager-gnome
openssh-client
python3
python3-pip
python3-venv
sudo
tmux
wget
xdotool
thunar
yad
BASE

# Add packages from Dockerfile — merge with actual base
EXTRA_FILE="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/arinanolabs-extra.txt"
proot-distro login arinanolabs -- bash -c 'dpkg -l 2>/dev/null | grep "^ii" | awk "{print \$2}"' \
    | grep -v -f "$BASE_PKGS" - > "$EXTRA_FILE" 2>/dev/null || true

EXTRA=$(cat "$EXTRA_FILE" 2>/dev/null | head -30 | tr '\n' ' ')

# ── Detect custom dotfiles ──────────────────────────────────
DOTFILES=""
for df in .bashrc .bash_aliases .gitconfig; do
    src="$ROOTFS/home/admin/$df"
    if [ -f "$src" ]; then
        # Check if file differs from shipped config (skip if identical to configs-target)
        DOTFILES="$DOTFILES\n    - $df"
    fi
done

# ── Write manifest ──────────────────────────────────────────
cat > "$MANIFEST" <<YAML
# arinanoX User Manifest
# Generated: $(date -Iseconds)
# This file tracks your customizations so they survive updates.
#
# Run after customizing:  arinanolabs snapshot create
# Run after update:       arinanolabs install   (auto-applied)

# User-installed packages (auto-detected from apt-mark)
packages:
$(echo "$EXTRA" | tr ' ' '\n' | grep -v "^$" | sed 's/^/  - /')

# Custom dotfiles (tracked for backup/sync)
dotfiles:$(echo -e "$DOTFILES")
YAML

echo ""
echo "  ✓ Manifest written: $MANIFEST"
echo ""
echo "  Review & customize it, then:"
echo "    arinanolabs snapshot create    # checkpoint before update"
echo "    arinanolabs update             # update + re-apply"

cat "$MANIFEST"
