FROM debian:13

# ═══════════════════════════════════════════════════════════════
#  arinanoLabs — vanilla baseline
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
#     symptom. Size is a phase 2 concern.
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
RUN apt-get update && \
    apt-get install -y \
        ca-certificates locales sudo && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Desktop ────────────────────────────────────────────────────
# dbus-x11 provides dbus-launch. Guides single it out as the package
# whose absence causes strange, hard-to-attribute failures.
RUN apt-get update && \
    apt-get install -y \
        xfce4 \
        xfce4-terminal \
        dbus-x11 && \
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
