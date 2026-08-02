#!/bin/bash
# Enable AT-SPI accessibility (required for onboard to detect text-field focus)
gsettings set org.gnome.desktop.interface toolkit-accessibility true

# Onboard auto-show settings
gsettings set org.onboard.auto-show enabled true
gsettings set org.onboard.auto-show hide-on-key-press true
gsettings set org.onboard xembed-onboard true
gsettings set org.onboard status-icon-provider 'GtkStatusIcon'
gsettings set org.onboard key-label-font 'Noto Sans'
gsettings set org.onboard theme 'Droid'
gsettings set org.onboard layout '/usr/share/onboard/layouts/Compact.onboard'

# Start hidden — auto-show will pop it up when a text field gets focus
# and hide it again once focus leaves / a hardware key is pressed.
exec onboard --start-hidden
