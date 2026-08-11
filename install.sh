#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  arinanoLabs — bootstrap entry point
#  Usage: curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.sh | bash
#
#  Guarantees git and Python, then hands over to install.py, which does
#  the actual install. Keep this file boring: it is the one thing that
#  cannot assume anything about the machine.
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

INSTALLER_URL="https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.py"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${CYAN}>>>${NC} $1"; }
ok()   { echo -e "${GREEN}  ok${NC} $1"; }
die()  { echo -e "${RED}  failed${NC} $1"; exit 1; }

pkg_install() {
    if command -v pkg &>/dev/null; then
        pkg install -y "$@"
    elif command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y "$@"
    elif command -v brew &>/dev/null; then
        brew install "$@"
    else
        die "no supported package manager; install manually: $*"
    fi
}

ensure_git() {
    command -v git &>/dev/null || { info "Installing git"; pkg_install git; }
    command -v git &>/dev/null || die "git is still missing"
    ok "git $(git --version | awk '{print $3}')"
}

ensure_python() {
    if command -v python3 &>/dev/null; then
        PYTHON="python3"
    elif command -v python &>/dev/null; then
        PYTHON="python"
    else
        info "Installing Python"
        pkg_install python
        PYTHON="python3"
    fi
    command -v "$PYTHON" &>/dev/null || die "Python is still missing"

    if ! $PYTHON -m pip --version &>/dev/null; then
        info "Installing pip"
        $PYTHON -m ensurepip --upgrade &>/dev/null \
            || curl -sS https://bootstrap.pypa.io/get-pip.py | $PYTHON \
            || die "could not install pip"
    fi
    ok "Python $($PYTHON --version 2>&1 | awk '{print $2}') with pip"
}

# Prefer the copy next to this script when run from a checkout; otherwise
# fetch it, since the usual entry point is curl | bash with no repo on disk.
run_installer() {
    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"

    if [ -n "$here" ] && [ -f "$here/install.py" ]; then
        info "Running installer from $here"
        exec "$PYTHON" "$here/install.py"
    fi

    info "Downloading installer"
    local tmp
    tmp="$(mktemp -t arinanolabs-install.XXXXXX.py)"
    trap 'rm -f "$tmp"' EXIT
    curl -fsSL "$INSTALLER_URL" -o "$tmp" || die "could not download install.py"
    exec "$PYTHON" "$tmp"
}

main() {
    echo
    echo -e "${CYAN}===========================================${NC}"
    echo -e "${CYAN}  arinanoLabs Bootstrap${NC}"
    echo -e "${CYAN}===========================================${NC}"
    echo
    ensure_git
    ensure_python
    run_installer
}

main "$@"
