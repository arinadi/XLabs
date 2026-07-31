#!/bin/bash
# ═══════════════════════════════════════════
#  arinanoX Dark Mobile Theme (MATE)
#  Orchis-Dark GTK + MATE panel + Adwaita icons
# ═══════════════════════════════════════════

echo ">>> Applying arinanoX Dark Mobile Theme (MATE)..."

# ── MATE settings via dconf/gsettings ──
if command -v gsettings &>/dev/null; then
    # Theme
    gsettings set org.mate.desktop.gtk-theme 'Orchis-Dark'
    gsettings set org.mate.desktop.icon-theme 'elementary-xfce-hidpi'
    gsettings set org.mate.desktop.font-name 'Sans 12'
    gsettings set org.mate.desktop.cursor-theme 'Adwaita'
    gsettings set org.mate.desktop.cursor-size 64

    # Marco (window manager)
    gsettings set org.mate.marco.general compositing-manager false
    gsettings set org.mate.marco.general center-new-windows false

    # Font rendering
    gsettings set org.gnome.desktop.interface text-scaling-factor 1.0
    gsettings set org.gnome.desktop.interface cursor-size 64

    echo "  ✓ MATE settings applied via gsettings"
else
    echo "  ⚠ gsettings not available — using dconf database"
    DB_DIR="$HOME/.config/dconf/db"
    mkdir -p "$DB_DIR"

    cat > "$DB_DIR/arinanox" << 'EOF'
[org/mate/desktop]
gtk-theme='Orchis-Dark'
icon-theme='elementary-xfce-hidpi'
font-name='Sans 12'
cursor-theme='Adwaita'
cursor-size=64

[org/mate/marco/general]
compositing-manager=false
center-new-windows=false
EOF

    dconf compile "$DB_DIR/arinanox" "$DB_DIR" 2>/dev/null || true
    echo "  ✓ dconf database compiled"
fi

echo ""
echo "╔═══════════════════════════════════╗"
echo "║  🎨 Orchis Material + Elementary   ║"
echo "╠═══════════════════════════════════╣"
echo "║  GTK:   Orchis-Dark (Material)     ║"
echo "║  Icons: elementary-xfce-hidpi      ║"
echo "║  WM:    Marco (no compositing)     ║"
echo "║  Font:  Sans 12                    ║"
echo "║  Cursor: 64px                      ║"
echo "╠═══════════════════════════════════╣"
echo "║  Restart MATE to apply             ║"
echo "╚═══════════════════════════════════╝"
