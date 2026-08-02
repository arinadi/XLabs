"""Install logic for arinanoLabs."""

import os
import sys
import subprocess
import urllib.request
from pathlib import Path

from .ui import (
    console, clear, run_cmd, show_banner, show_panel,
    show_progress_download, show_error, show_success, show_warning
)
from .mirror import ensure_mirror
from .gpu import detect_gpu, write_gpu_config, get_gpu_summary
from .welcome import show_post_install_info


# ── Config ─────────────────────────────────────────────────

REPO_URL = "https://raw.githubusercontent.com/arinadi/arinanoLabs/main"
PROOT_DISTRO = "debian"
CONTAINER_NAME = "arinanox"
ADMIN_USER = "admin"


# ── Install Steps ──────────────────────────────────────────

def install():
    """Main install flow."""
    clear()
    show_banner()

    console.print("\n[bold cyan]Installing arinanoLabs...[/bold cyan]\n")

    steps = [
        ("Updating system packages", step_update_system),
        ("Installing proot-distro", step_install_proot),
        ("Installing Termux:X11", step_install_x11),
        ("Installing audio (PulseAudio)", step_install_audio),
        ("Installing GPU drivers", step_install_gpu),
        ("Creating Debian container", step_create_container),
        ("Installing desktop environment", step_install_desktop),
        ("Installing dev tools", step_install_devtools),
        ("Configuring GPU", step_configure_gpu),
        ("Setting up user", step_setup_user),
        ("Installing launcher scripts", step_install_launchers),
    ]

    for i, (name, step_fn) in enumerate(steps, 1):
        console.print(f"\n[bold][{i}/{len(steps)}] {name}...[/bold]")
        try:
            success = step_fn()
            if success:
                console.print(f"  [green]✓ Done[/green]")
            else:
                console.print(f"  [yellow]⚠ Skipped or warning[/yellow]")
        except Exception as e:
            console.print(f"  [red]✗ Failed: {e}[/red]")
            if not continue_on_error():
                sys.exit(1)

    # Show completion
    show_post_install_info()


def continue_on_error() -> bool:
    """Ask user if they want to continue on error."""
    console.print()
    response = input("  Continue anyway? [y/N] ").strip().lower()
    return response in ("y", "yes")


# ── Step Implementations ───────────────────────────────────

def step_update_system() -> bool:
    """Update system packages."""
    rc, _ = run_cmd("pkg update -y", timeout=120)
    return rc == 0


def step_install_proot() -> bool:
    """Install proot-distro."""
    rc, _ = run_cmd("pkg install -y proot-distro", timeout=60)
    return rc == 0


def step_install_x11() -> bool:
    """Install Termux:X11 and dependencies."""
    packages = [
        "termux-x11-nightly",
        "x11-repo",
        "tur-repo",
        "xorg-xrandr",
        "netcat-openbsd",
    ]
    rc, _ = run_cmd(f"pkg install -y {' '.join(packages)}", timeout=120)
    return rc == 0


def step_install_audio() -> bool:
    """Install PulseAudio."""
    rc, _ = run_cmd("pkg install -y pulseaudio", timeout=60)
    return rc == 0


def step_install_gpu() -> bool:
    """Install GPU drivers."""
    packages = [
        "mesa-zink",
        "mesa-vulkan-icd-freedreno",
        "vulkan-loader-android",
        "virglrenderer-android",
        "angle-android",
    ]
    rc, _ = run_cmd(f"pkg install -y {' '.join(packages)}", timeout=120)
    return rc == 0


def step_create_container() -> bool:
    """Create Debian proot container."""
    # Check if already exists
    rc, _ = run_cmd(f"proot-distro list | grep {CONTAINER_NAME}")
    if rc == 0:
        console.print("  [dim]Container already exists, skipping...[/dim]")
        return True

    # Install Debian
    rc, output = run_cmd(f"proot-distro install {PROOT_DISTRO}", timeout=300)
    if rc != 0:
        console.print(f"  [red]{output}[/red]")
        return False

    # Rename to arinanox
    rc, _ = run_cmd(f"proot-distro rename {PROOT_DISTRO} {CONTAINER_NAME}", timeout=30)
    return rc == 0


def step_install_desktop() -> bool:
    """Install MATE desktop inside container."""
    packages = [
        "mate-desktop-environment",
        "mate-terminal",
        "mate-system-monitor",
        "pluma",
        "eom",
        "firefox-esr",
        "thunar",
        "adwaita-icon-theme",
    ]

    install_cmd = f"""
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y --no-install-recommends {' '.join(packages)}
        apt-get clean
        rm -rf /var/lib/apt/lists/*
    """

    rc, output = run_cmd(
        f"proot-distro login {CONTAINER_NAME} -- bash -c '{install_cmd}'",
        timeout=600
    )
    return rc == 0


def step_install_devtools() -> bool:
    """Install development tools inside container."""
    packages = [
        "git",
        "python3",
        "python3-pip",
        "build-essential",
        "cmake",
        "htop",
        "tmux",
        "curl",
        "wget",
    ]

    install_cmd = f"""
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y --no-install-recommends {' '.join(packages)}
        apt-get clean
        rm -rf /var/lib/apt/lists/*
    """

    rc, output = run_cmd(
        f"proot-distro login {CONTAINER_NAME} -- bash -c '{install_cmd}'",
        timeout=300
    )
    return rc == 0


def step_configure_gpu() -> bool:
    """Configure GPU based on detection."""
    gpu = detect_gpu()
    console.print(f"  Detected: {get_gpu_summary(gpu)}")

    config_path = write_gpu_config(gpu)
    console.print(f"  Config written to: {config_path}")
    return True


def step_setup_user() -> bool:
    """Setup admin user in container."""
    setup_cmd = f"""
        useradd -m -s /bin/bash {ADMIN_USER} 2>/dev/null || true
        echo "{ADMIN_USER}:{ADMIN_USER}" | chpasswd
        echo "{ADMIN_USER} ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/{ADMIN_USER}
        chmod 0440 /etc/sudoers.d/{ADMIN_USER}
    """

    rc, _ = run_cmd(
        f"proot-distro login {CONTAINER_NAME} -- bash -c '{setup_cmd}'",
        timeout=30
    )
    return rc == 0


def step_install_launchers() -> bool:
    """Install alabs launcher to Termux home."""
    alabs_script = os.path.expanduser("~/.local/bin/alabs")
    os.makedirs(os.path.dirname(alabs_script), exist_ok=True)

    installer_dir = os.path.dirname(os.path.dirname(__file__))

    with open(alabs_script, "w") as f:
        f.write(f"""#!/bin/bash
# arinanoLabs TUI launcher
python3 -c "
import sys
sys.path.insert(0, '{installer_dir}')
from installer.menu import main
main()
"
""")
    os.chmod(alabs_script, 0o755)

    # Add to PATH if not already
    bashrc = os.path.expanduser("~/.bashrc")
    path_line = 'export PATH="$HOME/.local/bin:$PATH"'
    try:
        with open(bashrc, "r") as f:
            if path_line not in f.read():
                with open(bashrc, "a") as f:
                    f.write(f"\n# arinanoLabs\n{path_line}\n")
    except FileNotFoundError:
        with open(bashrc, "w") as f:
            f.write(f"# arinanoLabs\n{path_line}\n")

    return True
