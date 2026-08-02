export DISPLAY=:0
export XDG_RUNTIME_DIR=/tmp
export NO_AT_BRIDGE=1
export LIBGL_ALWAYS_SOFTWARE=1
# Firefox: suppress sandbox video device spam in proot
export MOZ_DISABLE_CONTENT_SANDBOX=1

# Clean PATH from Termux pollution (bind-mount ke /data/data/com.termux/...)
# Hanya proot-native binary (glibc) — Termux binary (bionic) tidak bisa jalan
# Guard di akhir .bashrc akan stripping path Termux dari PATH
TARGET_PATH=/home/admin/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH=$TARGET_PATH

# NVM Initialization (if exists)
export NVM_DIR="$HOME/.config/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

# Python: pip user installs
# Node: npm global installs
export PATH="$PATH:$HOME/.local/bin"

alias update='sudo apt-get update && sudo apt-get upgrade -y'
alias ll='ls -la'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias cls='clear'
alias df='df -h'
alias free='free -h'
alias ports='ss -tlnp'
alias myip='curl -s ifconfig.me && echo'

# ──── Preventif: hapus Termux bind-mount dari PATH ──────────
# termux-profile.sh (/etc/profile.d/) nambahin Termux ke PATH,
# tapi binary Termux (bionic libc) ga bisa jalan di proot (glibc).
# Guard ini stripping path Termux dari PATH di akhir init.
export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "/data/data/com.termux" | tr '\n' ':' | sed 's/:$//')
