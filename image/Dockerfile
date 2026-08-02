FROM debian:13

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ═══════════════════════════════════════════════
# Layer 1  BASE
# ═══════════════════════════════════════════════
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        dialog locales ca-certificates sudo \
        curl wget zip unzip jq tree less && \
    apt-get clean && rm -rf /var/lib/apt/lists/* \
    /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
    /usr/share/locale/* /var/cache/apt/archives/*

# ═══════════════════════════════════════════════
# Layer 2  XFCE4 DESKTOP
# ═══════════════════════════════════════════════
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        dbus-x11 \
        xfce4 xfce4-goodies \
        thunar thunar-archive-plugin \
        xfce4-terminal xfce4-panel \
        xfce4-session xfce4-settings \
        xfce4-notifyd xfce4-screenshooter \
        mousepad ristretto \
        menu gnome-keyring && \
    apt-get clean && rm -rf /var/lib/apt/lists/* \
    /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
    /usr/share/locale/* /var/cache/apt/archives/*

# ═══════════════════════════════════════════════
# Layer 3  GUI EXTRAS
# ═══════════════════════════════════════════════
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        pulseaudio-utils x11-xserver-utils \
        xdotool yad gnupg && \
    apt-get clean && rm -rf /var/lib/apt/lists/* \
    /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
    /usr/share/locale/* /var/cache/apt/archives/*

# ═══════════════════════════════════════════════
# Layer 4  BROWSER
# ═══════════════════════════════════════════════
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        firefox-esr && \
    apt-get clean && rm -rf /var/lib/apt/lists/* \
    /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
    /usr/share/locale/* /var/cache/apt/archives/*

# ═══════════════════════════════════════════════
# Layer 5  DEV TOOLS
# ═══════════════════════════════════════════════
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git python3-pip python3-venv python3-dev \
        build-essential cmake pkg-config \
        htop tmux openssh-client \
        zsh fzf ripgrep bat lazygit && \
    apt-get clean && rm -rf /var/lib/apt/lists/* \
    /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
    /usr/share/locale/* /var/cache/apt/archives/*

# Install Oh My Zsh
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended

# ═══════════════════════════════════════════════
# Layer 6  NODE.JS
# ═══════════════════════════════════════════════
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/* \
    /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
    /usr/share/locale/* /var/cache/apt/archives/*

# ═══════════════════════════════════════════════
# Layer 7  TOUCHSCREEN / HiDPI SUPPORT
# ═══════════════════════════════════════════════
# NOTE: touchegg is intentionally NOT installed — it is not packaged for
# Debian (Ubuntu PPA / Fedora / Arch / openSUSE only) and would fail to
# build here. It's also unnecessary in a proot-distro + Termux:X11 setup:
# this container is an X11 *client* only (no /dev/input access), so all
# real touch/gesture handling happens on the Android host side via the
# Termux:X11 app itself (see its "Touchscreen input mode" setting).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        onboard \
        at-spi2-core \
        gsettings-desktop-schemas \
        dconf-cli \
        dconf-gsettings-backend \
        libglib2.0-bin \
        xinput \
        fonts-noto-core \
        fonts-noto-color-emoji \
        materia-gtk-theme \
        papirus-icon-theme && \
    apt-get clean && rm -rf /var/lib/apt/lists/* \
    /usr/share/doc/* /usr/share/man/* /usr/share/info/* \
    /usr/share/locale/* /var/cache/apt/archives/*

# Accessibility bridge needed for onboard's auto-show-on-focus feature
ENV GTK_MODULES=gail:atk-bridge
ENV NO_AT_BRIDGE=0

# ═══════════════════════════════════════════════
# Layer 8  USER + CONFIGS
# ═══════════════════════════════════════════════
RUN useradd -m -s /bin/bash admin && \
    echo "admin:admin" | chpasswd && \
    echo "admin ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/admin && \
    chmod 0440 /etc/sudoers.d/admin

COPY configs-target/home/ /home/

RUN chmod +x /home/admin/.config/autostart-scripts/*.sh && \
    chown -R admin:admin /home/admin && \
    sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && locale-gen

ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

CMD ["/bin/bash"]
