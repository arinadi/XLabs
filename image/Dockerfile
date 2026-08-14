FROM debian:13

# ═══════════════════════════════════════════════════════════════
#  XLabs — vanilla baseline
#
#  Phase 1: match the established Termux + proot + XFCE recipe as
#  closely as possible, and nothing else. The previous image carried a
#  large amount of tuning — dev toolchain, themes, on-screen keyboard,
#  a pre-baked panel layout — and the desktop never came up, so this
#  strips back to a build whose shape is known to work elsewhere.
#
#  Two deliberate differences from the previous image:
#
#  1. No --no-install-recommends. Every published guide installs these
#     packages with recommends enabled. Depends alone gave a container
#     where xfce4-session started and never launched xfwm4 or
#     xfdesktop, and a missing runtime recommendation fits that
#     symptom. Recommends stay on; specific packages are excluded below
#     instead, per docs/image-optimization.md — proot has no cgroups,
#     no namespaces and no real hardware, so systemd, disk/session
#     daemons (udisks2, upower, accountsservice), color management
#     (colord, xiccd) and network discovery (avahi-daemon) can never
#     do anything here. gvfs and a second audio server (pulseaudio or
#     pipewire-pulse, pulled by xfce4-pulseaudio-plugin) are excluded
#     too — the latter would otherwise fight the client-only PulseAudio
#     setup this image is built around (see installer/const.py).
#
#  2. No baked-in user configuration. The panel layout, xsettings,
#     onboard autostart and battery monitor are gone; XFCE creates its
#     own defaults on first run. They are recoverable from git history
#     if they turn out to be wanted again.
# ═══════════════════════════════════════════════════════════════

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ── Base ───────────────────────────────────────────────────────
# Verified against a real-device audit (issue #6): a freshly provisioned
# container had no text editor, no version control, and none of these
# basic CLI utilities at all — confirmed with a podman dry-run against
# this exact package set, not taken on the audit's word (it also
# self-contradicted on `sudo`, already installed below). Every package
# here is small (largest is wget at ~3.8 MB installed; the rest are under
# 1 MB each) and is the kind of thing assumed present on any Linux
# desktop, unlike the heavier/situational dev toolchain (build-essential,
# python3-pip, nodejs, vim/neovim, tmux...) that stays Store-only
# (packages.py CURATED_PACKAGES) per the vanilla-baseline / image-size
# rationale above. git's own Recommends pulls in openssh-client (git+ssh
# remotes), less and patch for free.
RUN apt-get update && \
    apt-get install -y \
        ca-certificates locales sudo git nano \
        curl wget zip unzip htop tree jq rsync && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Desktop ────────────────────────────────────────────────────
# dbus-x11 provides dbus-launch. Guides single it out as the package
# whose absence causes strange, hard-to-attribute failures.
#
# The `pkg-` entries exclude recommends that cannot function here. Read
# from the build log rather than guessed at — an earlier attempt excluded
# `xorg`, which apt reported was never installed in the first place, and
# saved 13 MiB of a 620 MiB image.
#
#   xserver-xorg + video/input drivers — the X server is Termux:X11 on the
#     Android side. The drivers are for amdgpu, ati, nouveau and radeon:
#     desktop GPUs that cannot exist on this device.
#   initramfs-tools — there is no kernel here to build an initramfs for,
#     and it drags in dracut, klibc, busybox, cpio and a C preprocessor.
#
# Recommends stay enabled otherwise, which was the point of the vanilla
# baseline. Exclusions must be repeated per layer; apt does not remember.
#
# Split in two so a dropped connection retries a chunk rather than the
# whole desktop. proot-distro pulls layer by layer with no resume inside
# one, and this is a phone on mobile data.
RUN apt-get update && \
    apt-get install -y \
        xfwm4 xfce4-session xfce4-settings xfconf \
        xorg- xserver-xorg- xserver-xorg-core- \
        xserver-xorg-video-all- xserver-xorg-input-all- \
        xserver-xorg-legacy- initramfs-tools- \
        systemd-sysv- systemd-timesyncd- upower- colord- xiccd- && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# xfce4's own Recommends (not its Depends — those are the session itself,
# untouched) are desktop-base, mate-polkit, tango-icon-theme, thunar-volman
# and xfce4-notifyd. Two of those are excluded here:
#
#   desktop-base   — Debian's splash/wallpaper artwork. Cosmetic only; XFCE
#     falls back to a plain background without it.
#   thunar-volman  — auto-mounts removable media on insertion. There is no
#     real block device to insert here.
#
# mate-polkit, tango-icon-theme and xfce4-notifyd stay: the bug that made
# xfwm4/xfdesktop never launch (see above) came from disabling recommends
# broadly, and these three are visible or fallback-relevant enough — a
# privilege dialog, panel/file-manager icons, desktop notifications — that
# trimming them needs a real device test to confirm the session still
# comes up, not just a guess from a dependency list.
RUN apt-get update && \
    apt-get install -y \
        xfce4 \
        xfce4-terminal \
        dbus-x11 \
        xorg- xserver-xorg- xserver-xorg-core- \
        xserver-xorg-video-all- xserver-xorg-input-all- \
        xserver-xorg-legacy- initramfs-tools- \
        desktop-base- thunar-volman- \
        systemd-sysv- systemd-timesyncd- upower- colord- xiccd- \
        udisks2- gvfs- gvfs-daemons- avahi-daemon- \
        pulseaudio- pipewire-pulse- accountsservice- && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Theme ──────────────────────────────────────────────────────
# breeze-gtk-theme provides Breeze Dark: pure-CSS GTK3, no legacy GTK2
# engine deps (unlike gnome-themes-extra), and actively maintained
# upstream via KDE Plasma releases. Installed only; not set as default,
# per the no-baked-in-configuration rule above — pick it via
# xfce4-settings > Appearance on first run.
RUN apt-get update && \
    apt-get install -y \
        breeze-gtk-theme && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── X11 client tools, GL userspace, audio client ───────────────
RUN apt-get update && \
    apt-get install -y \
        x11-xserver-utils \
        libgl1-mesa-dri libegl1 libgles2 libglx-mesa0 mesa-utils \
        pulseaudio-utils && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Browser ────────────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y \
        firefox-esr && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── User ───────────────────────────────────────────────────────
RUN useradd -m -s /bin/bash admin && \
    echo "admin:admin" | chpasswd && \
    echo "admin ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/admin && \
    chmod 0440 /etc/sudoers.d/admin

RUN sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    locale-gen

ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

CMD ["/bin/bash"]
