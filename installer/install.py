"""Install logic for arinanoLabs."""

import os
import sys
import subprocess
import urllib.request
from pathlib import Path

from .ui import (
    console, clear, read_input, run_cmd, run_cmd_stream, show_banner,
    show_panel, show_progress_download, show_error, show_success, show_warning
)
from .mirror import ensure_mirror
from .gpu import detect_gpu, write_gpu_config, get_gpu_summary
from .welcome import show_post_install_info


# ── Config ─────────────────────────────────────────────────

REPO_URL = "https://raw.githubusercontent.com/arinadi/arinanoLabs/main"
PROOT_DISTRO = "debian"
CONTAINER_NAME = "arinanolabs"
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
        ("Pulling arinanoLabs image", step_pull_image),
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
    console.print()
    console.print("[bold green]═══ Installation Complete ═══[/bold green]")
    console.print("  Run [bold]alabs[/bold] to open the TUI menu\n")


def continue_on_error() -> bool:
    """Ask user if they want to continue on error."""
    console.print()
    response = read_input("  Continue anyway? [y/N] ").lower()
    return response in ("y", "yes")


# ── Step Implementations ───────────────────────────────────

def step_update_system() -> bool:
    """Update system packages."""
    rc = run_cmd_stream("pkg update -y")
    return rc == 0


def step_install_proot() -> bool:
    """Install proot-distro."""
    rc = run_cmd_stream("pkg install -y proot-distro")
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
    rc = run_cmd_stream(f"pkg install -y {' '.join(packages)}")
    return rc == 0


def step_install_audio() -> bool:
    """Install PulseAudio."""
    rc = run_cmd_stream("pkg install -y pulseaudio")
    return rc == 0


def step_install_gpu() -> bool:
    """Install GPU drivers."""
    packages = [
        "mesa-zink",
        "vulkan-loader-android",
        "virglrenderer-android",
        "angle-android",
    ]
    rc = run_cmd_stream(f"pkg install -y {' '.join(packages)}")
    return rc == 0


def step_pull_image() -> bool:
    """Pull arinanoLabs image from GHCR (Debian + MATE + dev tools pre-installed)."""
    # Check if already exists
    rc, _ = run_cmd(f"proot-distro list | grep {CONTAINER_NAME}")
    if rc == 0:
        console.print("  [dim]Container already exists, skipping...[/dim]")
        return True

    # Pull from GitHub Container Registry
    image_ref = "ghcr.io/arinadi/arinanolabs:latest"
    console.print(f"  [dim]Pulling {image_ref} (this may take a few minutes)...[/dim]")
    rc = run_cmd_stream(f"proot-distro install {image_ref} --name {CONTAINER_NAME}", timeout=900)

    if rc != 0:
        console.print("\n  [red]✗ Failed to pull image.[/red]")
        console.print("  Possible causes:")
        console.print("    • No internet connection")
        console.print("    • GHCR package is private (needs to be public)")
        console.print("    • Download timed out")
        return False

    # Verify container was created
    rc, _ = run_cmd(f"proot-distro list | grep {CONTAINER_NAME}")
    if rc != 0:
        console.print("\n  [red]✗ Image pulled but container not created.[/red]")
        console.print("  Run manually: proot-distro install ghcr.io/arinadi/arinanolabs:latest --name arinanolabs")
        return False

    return True


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
