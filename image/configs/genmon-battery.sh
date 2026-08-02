#!/bin/bash
# ═══════════════════════════════════════════
#  Battery Monitor (MATE/XFCE compatible)
#  Panel plugin that shows 🔋 percentage
# ===========================================
#  MATE: mate-panel → Add → Notification Area
#  XFCE: xfce4-panel → Add → Generic Monitor
#  Command: bash ~/.arinanolabs/tools/genmon-battery.sh
#  Interval: 30s
# ═══════════════════════════════════════════

# Read battery from sysfs (works in proot without Termux:API)
BAT_PATH="/sys/class/power_supply/battery"
if [ ! -d "$BAT_PATH" ]; then
    echo "<txt>🔌</txt><tool>No battery found</tool>"
    exit 0
fi

PCT=$(cat "$BAT_PATH/capacity" 2>/dev/null || echo "0")
STATUS=$(cat "$BAT_PATH/status" 2>/dev/null || echo "Unknown")

# Icon based on level
if   [ "$PCT" -ge 90 ]; then ICON="🔋"
elif [ "$PCT" -ge 60 ]; then ICON="🔋"
elif [ "$PCT" -ge 30 ]; then ICON="🔋"
elif [ "$PCT" -ge 15 ]; then ICON="🪫"
else                          ICON="🪫"; fi

# Charging indicator
[ "$STATUS" = "Charging" ] && ICON="⚡"

echo "<txt>${ICON} ${PCT}%</txt>"
echo "<tool>Battery: ${PCT}% (${STATUS})</tool>"
