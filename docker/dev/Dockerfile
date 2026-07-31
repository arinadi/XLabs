FROM termux/termux-docker

# ═══════════════════════════════════════════════
#  arinanoX Dev — Termux + proot-distro + MATE
# ═══════════════════════════════════════════════

# ── Termux packages ──────────────────────────────
RUN pkg update -y && pkg install -y \
        proot-distro \
        x11-repo \
        pulseaudio \
        rsync \
        python3 \
        curl \
        git \
        openssh \
    && pkg clean

# ── Debian proot container ───────────────────────
RUN proot-distro install debian

# ── MATE + dev tools inside proot ────────────────
RUN proot-distro login debian -- bash -c "\
    apt-get update && \
    apt-get install -y --no-install-recommends \
        mate-desktop-environment \
        mate-terminal \
        mate-system-monitor \
        mate-utils \
        mate-applets \
        pluma \
        eom \
        atril \
        engrampa \
        marco \
        dbus-x11 \
        pulseaudio-utils \
        network-manager-gnome \
        git \
        python3-pip \
        python3-venv \
        build-essential \
        cmake \
        pkg-config \
        htop \
        tmux \
        curl \
        wget \
        jq \
        tree \
        less && \
    apt-get clean && rm -rf /var/lib/apt/lists/*"

# ── Setup admin user inside proot ────────────────
RUN proot-distro login debian -- bash -c "\
    useradd -m -s /bin/bash admin && \
    echo 'admin:admin' | chpasswd && \
    echo 'admin ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/admin && \
    chmod 0440 /etc/sudoers.d/admin"

# ── Working directory ────────────────────────────
WORKDIR /data/data/com.termux/files/home

CMD ["/bin/bash"]
