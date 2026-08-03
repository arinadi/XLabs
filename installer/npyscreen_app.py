"""arinaLabs TUI — Rich-based, clean and elegant."""

import os
import sys
import subprocess

from rich.panel import Panel
from rich.table import Table
from rich import box

from .ui import (
    console, clear, get_version, run_cmd, is_installed,
    show_banner, PROOT_DIR,
)


def is_running() -> bool:
    rc, _ = run_cmd("pgrep -f 'xfce4-session|startxfce4'")
    return rc == 0


def wait_key():
    console.print("\n  [dim]Press Enter to return...[/dim]")
    if sys.stdin.isatty():
        input()


# ── Menu ───────────────────────────────────────────────────

def show_menu():
    clear()
    v = get_version()

    table = Table(
        box=box.ROUNDED, show_header=False, border_style="cyan",
        padding=(0, 1), title=f"[bold cyan]📱 arinanoLabs[/bold cyan] [dim]v{v}[/dim]",
        title_justify="center",
    )
    table.add_column("key", style="bold cyan", width=3)
    table.add_column("item")
    table.add_row("1", "▶️  Start Desktop")
    table.add_row("2", "⏹️  Stop Desktop")
    table.add_row("3", "🔄  Update")
    table.add_row("4", "🧰  Extra Tools")
    table.add_row("5", "📊  Status")
    table.add_row("6", "🗑️   Reset (Clean Install)")
    table.add_row("7", "🧹  Clean Image Cache")
    table.add_row("", "")
    table.add_row("0", "🚪  Exit")
    console.print()
    console.print(table)
    console.print()


# ── Start ──────────────────────────────────────────────────

def handle_start():
    from .start import (
        is_running as check, start_pulseaudio, load_audio_modules,
        start_virgl, start_x11, wait_for_x11, start_xfce4,
    )

    clear()
    console.print("[bold cyan]▶️  Starting Desktop[/bold cyan]\n")

    if check():
        console.print("[yellow]⚠ Desktop is already running![/yellow]")
        wait_key()
        return

    steps = [
        ("Starting PulseAudio", start_pulseaudio),
        ("Loading audio modules", load_audio_modules),
        ("Starting virgl renderer", start_virgl),
        ("Starting X11 server", start_x11),
        ("Waiting for X11 socket", wait_for_x11),
        ("Launching Xfce4 desktop", start_xfce4),
    ]

    for name, fn in steps:
        console.print(f"  [cyan]→[/cyan] {name}...", end=" ")
        try:
            ok = fn()
            console.print("[green]✓[/green]" if ok else "[yellow]⚠[/yellow]")
        except Exception as e:
            console.print(f"[red]✗ {e}[/red]")

    console.print()
    if check():
        console.print("[green bold]✓ Desktop started![/green bold]")
        console.print("[dim]Open Termux:X11 app to see your desktop.[/dim]")
    else:
        console.print("[red]✗ Desktop may have failed to start[/red]")

    wait_key()


# ── Stop ───────────────────────────────────────────────────

def handle_stop():
    from .start import stop_desktop

    clear()
    console.print("[bold yellow]⏹️  Stopping Desktop[/bold yellow]\n")
    stop_desktop()
    console.print("[green]✓ Desktop stopped.[/green]")
    wait_key()


# ── Update ─────────────────────────────────────────────────

def handle_update():
    clear()
    console.print("[bold cyan]🔄  Updating[/bold cyan]\n")

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(os.path.join(repo, ".git")):
        console.print("[red]✗ Not a git repository[/red]")
        wait_key()
        return

    console.print("  [cyan]→[/cyan] Pulling latest changes...")
    result = subprocess.run(["git", "pull"], cwd=repo, capture_output=True, text=True)

    if result.returncode != 0:
        subprocess.run(["git", "fetch", "origin", "main"], cwd=repo, capture_output=True)
        result = subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=repo, capture_output=True, text=True)

    if result.returncode == 0:
        if "Already up to date" in result.stdout:
            console.print("  [green]✓ Already on latest version[/green]")
        else:
            console.print("  [green]✓ Updated![/green]")
            console.print("  [dim]Restart alabs to use the new version[/dim]")
    else:
        console.print("  [red]✗ Update failed[/red]")

    wait_key()


# ── Tools ──────────────────────────────────────────────────

def handle_tools():
    clear()
    console.print("[bold cyan]🧰  Extra Tools[/bold cyan]\n")
    console.print("  [cyan]1[/cyan]  Chromium Browser")
    console.print("  [cyan]2[/cyan]  VS Code (code-server)")
    console.print("  [cyan]3[/cyan]  Zsh + Oh My Zsh")
    console.print("  [cyan]4[/cyan]  Neovim")
    console.print("  [cyan]5[/cyan]  GitHub CLI")
    console.print("\n  [dim]Coming soon![/dim]")
    wait_key()


# ── Status ─────────────────────────────────────────────────

def handle_status():
    clear()
    console.print("[bold cyan]📊  System Status[/bold cyan]\n")

    container = is_installed()
    running = is_running()

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("label", style="bold", width=12)
    table.add_column("value")
    table.add_row("Container", "[green]✓ Installed[/green]" if container else "[red]✗ Not found[/red]")
    table.add_row("Desktop", "[green]● Running[/green]" if running else "[dim]○ Not running[/dim]")
    table.add_row("Version", get_version())
    console.print(table)

    wait_key()


# ── Reset ──────────────────────────────────────────────────

def handle_reset():
    """Reset container — clean install from latest image."""
    import subprocess

    clear()
    console.print("[bold red]🗑️   Reset (Clean Install)[/bold red]\n")
    console.print("[yellow]This will:[/yellow]")
    console.print("  • Stop the desktop if running")
    console.print("  • Delete the entire container (all data lost!)")
    console.print("  • Re-install from latest image\n")
    console.print("[red bold]All files, settings, and installed packages inside the container will be permanently deleted.[/red bold]\n")

    confirm = input("  Type 'yes' to confirm reset: ").strip().lower()
    if confirm != "yes":
        console.print("\n[dim]Reset cancelled.[/dim]")
        wait_key()
        return

    # Step 1: Stop desktop
    console.print("\n[cyan]→ Stopping desktop...[/cyan]")
    if is_running():
        handle_stop()
    else:
        console.print("  [dim]Desktop not running[/dim]")

    # Step 2: Kill all proot processes
    console.print("\n[cyan]→ Killing proot processes...[/cyan]")
    rc, _ = run_cmd("pkill -9 -f 'proot' 2>/dev/null")
    console.print("  [dim]done[/dim]")

    # Step 3: Remove container
    console.print("\n[cyan]→ Removing container...[/cyan]")
    rc, out = run_cmd("proot-distro remove arinanolabs 2>&1")
    if rc == 0:
        console.print("  [green]✓ Container removed[/green]")
    else:
        console.print(f"  [yellow]⚠ {out.strip()}[/yellow]")

    # Step 4: Re-install from latest image
    console.print("\n[cyan]→ Pulling latest image...[/cyan]")
    console.print("  [dim]This may take a few minutes...[/dim]")
    rc, out = run_cmd(
        "proot-distro install ghcr.io/arinadi/arinanolabs:latest "
        "--name arinanolabs 2>&1",
        timeout=900,
    )
    if rc == 0:
        console.print("  [green]✓ Image installed[/green]")
    else:
        console.print(f"  [red]✗ Install failed: {out.strip()}[/red]")
        wait_key()
        return

    console.print("\n[green bold]✓ Reset complete![/green bold]")
    console.print("[dim]Run Start to launch the desktop.[/dim]")
    wait_key()


# ── Clean Cache ────────────────────────────────────────────

def handle_clean_cache():
    """Remove proot-distro OCI image cache."""
    import shutil

    clear()
    console.print("[bold cyan]🧹  Clean Image Cache[/bold cyan]\n")

    cache_dir = "/data/data/com.termux/files/usr/var/lib/proot-distro/cache"
    if not os.path.exists(cache_dir):
        console.print("[dim]No cache found.[/dim]")
        wait_key()
        return

    # Show size
    size = subprocess.run(
        ["du", "-sh", cache_dir], capture_output=True, text=True
    )
    size_str = size.stdout.split()[0] if size.returncode == 0 else "unknown"
    console.print(f"  Cache: [yellow]{size_str}[/yellow]\n")

    console.print("[yellow]This will:[/yellow]")
    console.print("  • Stop desktop if running")
    console.print("  • Delete cached OCI image layers")
    console.print("  • Next install will re-download fresh image\n")

    confirm = input("  Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        console.print("\n[dim]Cancelled.[/dim]")
        wait_key()
        return

    # Stop desktop first
    if is_running():
        from .start import stop_desktop
        console.print("\n  [cyan]→[/cyan] Stopping desktop...")
        stop_desktop()
        console.print("  [green]✓ Desktop stopped[/green]")

    # Remove cache
    console.print("\n  [cyan]→[/cyan] Removing cache...")
    try:
        shutil.rmtree(cache_dir)
        console.print("  [green]✓ Cache cleared[/green]")
    except Exception as e:
        console.print(f"  [red]✗ Failed: {e}[/red]")
        wait_key()
        return

    console.print("\n[green]✓ Done![/green]")
    console.print("[dim]Next Reset or install will download a fresh image.[/dim]")
    wait_key()


# ── Main Loop ──────────────────────────────────────────────

def run_npyscreen():
    """Main TUI entry point."""
    handlers = {
        "1": handle_start,
        "2": handle_stop,
        "3": handle_update,
        "4": handle_tools,
        "5": handle_status,
        "6": handle_reset,
        "7": handle_clean_cache,
    }

    while True:
        show_menu()
        choice = input("  Select: ").strip()

        if choice == "0":
            clear()
            console.print("\n  [dim]Goodbye! 👋[/dim]\n")
            break
        elif choice in handlers:
            handlers[choice]()
        elif choice:
            console.print("\n  [yellow]Invalid option.[/yellow]")
            import time
            time.sleep(1)
