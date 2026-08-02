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
        mousepad ristretto xfburn \
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
# Layer 7  USER + CONFIGS
# ═══════════════════════════════════════════════
RUN useradd -m -s /bin/bash admin && \
    echo "admin:admin" | chpasswd && \
    echo "admin ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/admin && \
    chmod 0440 /etc/sudoers.d/admin

COPY configs-target/home/ /home/

RUN chown -R admin:admin /home/admin && \
    sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && locale-gen

ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

CMD ["/bin/bash"]
