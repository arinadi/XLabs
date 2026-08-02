#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  arinanoLabs Installer — Bootstrapper
#  Usage: curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.sh | bash
#
#  Flow: install git → clone/pull repo → run install.py
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

# ── Check/Install Git ──────────────────────────────────────
check_git() {
    if command -v git &>/dev/null; then
        ok "Git installed"
        return
    fi

    info "Installing git..."
    if command -v pkg &>/dev/null; then
        pkg install -y git
    elif command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y git
    elif command -v brew &>/dev/null; then
        brew install git
    else
        fail "Cannot install git. Please install manually."
    fi
    ok "Git installed"
}

# ── Clone or Pull ──────────────────────────────────────────
sync_repo() {
    if [ -d "$REPO_DIR/.git" ]; then
        info "Pulling latest changes..."
        cd "$REPO_DIR"
        git pull --ff-only || {
            warn "Pull failed, resetting..."
            git fetch origin main
            git reset --hard origin/main
        }
    else
        info "Cloning repository..."
        git clone --depth 1 "$REPO_URL" "$REPO_DIR"
        cd "$REPO_DIR"
    fi
    ok "Repository ready at $REPO_DIR"
}

# ── Run Installer ──────────────────────────────────────────
run_installer() {
    info "Launching TUI installer..."
    echo ""

    cd "$REPO_DIR"
    python install.py
}

# ── Main ────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${CYAN}  📱 arinanoLabs Installer${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo ""

    check_git
    sync_repo
    run_installer
}

main "$@"
