#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

echo ">>> Setting up MOTD..."

cat > /data/data/com.termux/files/usr/etc/motd << 'MOTDEOF'

==========================================
 📱 arinanoLabs
==========================================

 Launch TUI:
    alabs

 Start:
    bash ~/start.sh
 Stop:
    bash ~/stop.sh

 User: admin / Pass: admin
==========================================
MOTDEOF

echo ">>> MOTD updated."
