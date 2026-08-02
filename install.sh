#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  arinanoLabs Installer — Bootstrapper
#  Usage: curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.sh | bash
#
#  Flow: check deps → clone/pull repo → install libs → run install.py
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

REPO_URL="https://github.com/arinadi/arinanoLabs.git"
REPO_DIR="$HOME/arinanoLabs"

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}>>>${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
fail()  { echo -e "${RED}✗${NC} $1"; exit 1; }

# ── Package Manager ────────────────────────────────────────
pkg_install() {
    if command -v pkg &>/dev/null; then
        pkg install -y "$@"
    elif command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y "$@"
    elif command -v brew &>/dev/null; then
        brew install "$@"
    else
        fail "Cannot install packages. Please install manually: $*"
    fi
}

# ── Check/Install Git ──────────────────────────────────────
check_git() {
    if command -v git &>/dev/null; then
        ok "Git installed"
        return
    fi
    info "Installing git..."
    pkg_install git
    ok "Git installed"
}

# ── Check/Install Python ──────────────────────────────────
check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON="python3"
    elif command -v python &>/dev/null; then
        PYTHON="python"
    else
        info "Installing Python..."
        pkg_install python
        PYTHON="python3"
    fi
    ok "Python $($PYTHON --version 2>&1 | awk '{print $2}')"
}

# ── Check/Install pip ─────────────────────────────────────
check_pip() {
    if $PYTHON -m pip --version &>/dev/null; then
        PIP="$PYTHON -m pip"
    else
        info "Installing pip..."
        if command -v pkg &>/dev/null; then
            pkg install -y python
        else
            $PYTHON -m ensurepip --upgrade 2>/dev/null || {
                curl -sS https://bootstrap.pypa.io/get-pip.py | $PYTHON
            }
        fi
        PIP="$PYTHON -m pip"
    fi
    ok "pip installed"
}

# ── Install TUI libraries ────────────────────────────────
install_libs() {
    info "Installing TUI libraries..."
    $PIP install rich requests --quiet --break-system-packages 2>/dev/null || \
    $PIP install rich requests --quiet 2>/dev/null || \
    $PIP install rich requests --quiet --user 2>/dev/null || true
    ok "Libraries installed"
}

# ── Clone or Pull ──────────────────────────────────────────
sync_repo() {
    if [ -d "$REPO_DIR/.git" ]; then
        info "Pulling latest changes..."
        cd "$REPO_DIR"
        git pull --ff-only --depth=1 || {
            warn "Pull failed, resetting..."
            git fetch --depth=1 origin main
            git reset --hard origin/main
        }
    else
        info "Cloning repository..."
        git clone --depth 1 "$REPO_URL" "$REPO_DIR"
        cd "$REPO_DIR"
    fi
    ok "Repository ready"
}

# ── Run Installer ──────────────────────────────────────────
run_installer() {
    info "Launching TUI installer..."
    echo ""
    cd "$REPO_DIR"
    $PYTHON install.py

    # Refresh PATH so alabs is available in current session
    if [ -f "$HOME/.bashrc" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    fi
}

# ── Main ────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${CYAN}  📱 arinanoLabs Installer${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo ""

    check_git
    check_python
    check_pip
    install_libs
    sync_repo
    run_installer
}

main "$@"
