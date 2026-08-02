#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  arinanoLabs Installer — Bootstrapper
#  Usage: curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.sh | bash
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

REPO="https://raw.githubusercontent.com/arinadi/arinanoLabs/main"
INSTALL_DIR="$HOME/.arinanolabs"
PYTHON=""
PIP=""

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

# ── Check Python ────────────────────────────────────────────
check_python() {
    info "Checking Python..."

    if command -v python3 &>/dev/null; then
        PYTHON="python3"
    elif command -v python &>/dev/null; then
        PYTHON="python"
    else
        warn "Python not found. Installing..."
        install_python
        PYTHON="python3"
    fi

    local version
    version=$($PYTHON --version 2>&1 | awk '{print $2}')
    ok "Python $version"
}

install_python() {
    if command -v pkg &>/dev/null; then
        # Termux
        pkg install -y python
    elif command -v apt-get &>/dev/null; then
        # Debian/Ubuntu
        sudo apt-get update -qq
        sudo apt-get install -y python3 python3-pip
    elif command -v brew &>/dev/null; then
        # macOS
        brew install python
    else
        fail "Cannot install Python. Please install manually."
    fi
}

# ── Check pip ───────────────────────────────────────────────
check_pip() {
    info "Checking pip..."

    if $PYTHON -m pip --version &>/dev/null; then
        PIP="$PYTHON -m pip"
    elif command -v pip3 &>/dev/null; then
        PIP="pip3"
    elif command -v pip &>/dev/null; then
        PIP="pip"
    else
        warn "pip not found. Installing..."
        install_pip
        PIP="$PYTHON -m pip"
    fi

    ok "pip available"
}

install_pip() {
    if command -v pkg &>/dev/null; then
        pkg install -y python
    else
        $PYTHON -m ensurepip --upgrade 2>/dev/null || {
            curl -sS https://bootstrap.pypa.io/get-pip.py | $PYTHON
        }
    fi
}

# ── Check rich library ──────────────────────────────────────
check_rich() {
    info "Checking rich library..."

    if $PYTHON -c "import rich" 2>/dev/null; then
        ok "rich installed"
    else
        warn "rich not found. Installing..."
        $PIP install rich requests --quiet
        ok "rich installed"
    fi
}

# ── Download and run ────────────────────────────────────────
run_installer() {
    info "Downloading installer..."

    mkdir -p "$INSTALL_DIR"

    # Download all installer files
    local files=(
        "install.py"
        "VERSION"
        "requirements.txt"
        "installer/__init__.py"
        "installer/ui.py"
        "installer/menu.py"
        "installer/welcome.py"
        "installer/preflight.py"
        "installer/mirror.py"
        "installer/gpu.py"
        "installer/install.py"
        "installer/start.py"
    )

    for file in "${files[@]}"; do
        local dir
        dir=$(dirname "$INSTALL_DIR/$file")
        mkdir -p "$dir"

        if ! curl -sSf "${REPO}/${file}" -o "$INSTALL_DIR/$file"; then
            fail "Failed to download: $file"
        fi
    done

    ok "Installer downloaded"

    info "Launching TUI..."
    echo ""

    cd "$INSTALL_DIR"
    $PYTHON install.py
}

# ── Main ────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${CYAN}  📱 arinanoLabs Installer${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo ""

    check_python
    check_pip
    check_rich

    echo ""
    run_installer
}

main "$@"
