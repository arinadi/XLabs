"""Main TUI menu for arinanoLabs."""

import os
import sys

from .ui import (
    console, clear, read_input, is_installed, get_version, show_banner,
    show_panel, press_any_key, PROOT_DIR
)
from .welcome import (
    show_welcome, show_already_installed, get_user_choice,
    run_preflight, show_install_button
)
from .install import install
from .start import start_desktop, stop_desktop, is_running
from .gpu import detect_gpu, get_gpu_summary


def main():
    """Main entry point for TUI."""
    try:
        if is_installed():
            run_installed_menu()
        else:
            run_fresh_install()
    except KeyboardInterrupt:
        console.print("\n\n[dim]Exiting...[/dim]\n")
        sys.exit(0)


def run_fresh_install():
    """Run fresh install flow."""
    show_welcome()

    # Run pre-flight
    if not run_preflight():
        console.print("\n[red]Pre-flight checks failed. Fix issues and try again.[/red]")
        press_any_key()
        return

    # Show install button
    if not show_install_button():
        console.print("\n[dim]Installation cancelled.[/dim]")
        return

    # Run install
    install()


def run_installed_menu():
    """Run main menu when already installed."""
    while True:
        show_already_installed()
        choice = get_user_choice()

        if choice == "1":
            handle_start()
        elif choice == "2":
            handle_stop()
        elif choice == "3":
            handle_update()
        elif choice == "4":
            handle_tools()
        elif choice == "5":
            handle_status()
        elif choice == "6":
            handle_uninstall()
        elif choice == "0":
            console.print("\n[dim]Goodbye! 👋[/dim]\n")
            break
        else:
            console.print("\n[yellow]Invalid option. Try again.[/yellow]")
            press_any_key()


# ── Handlers ───────────────────────────────────────────────

def handle_start():
    """Handle start desktop."""
    clear()
    show_banner()
    start_desktop()
    press_any_key()


def handle_stop():
    """Handle stop desktop."""
    clear()
    show_banner()
    stop_desktop()
    press_any_key()


def handle_update():
    """Handle update — git pull from repo."""
    clear()
    show_banner()
    console.print("\n[bold]Updating arinanoLabs...[/bold]\n")

    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Check if git repo
    if not os.path.exists(os.path.join(repo_dir, ".git")):
        console.print("  [red]✗ Not a git repository. Reinstall via install.sh[/red]")
        press_any_key()
        return

    # Git pull (shallow — no history)
    import subprocess
    console.print("  [cyan]→[/cyan] Pulling latest changes...")

    # Try fast-forward first
    result = subprocess.run(
        ["git", "pull", "--ff-only", "--depth=1"],
        cwd=repo_dir, capture_output=True, text=True
    )

    # If diverged, reset to remote
    if result.returncode != 0 and "diverging" in (result.stderr + result.stdout).lower():
        console.print("  [dim]Local diverged, resetting to remote...[/dim]")
        subprocess.run(["git", "fetch", "--depth=1", "origin", "main"], cwd=repo_dir, capture_output=True)
        result = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            cwd=repo_dir, capture_output=True, text=True
        )

    if result.returncode == 0:
        console.print(f"  [green]✓ Updated[/green]")
        if "Already up to date" in result.stdout:
            console.print("  [dim]Already on latest version[/dim]")
        else:
            console.print("  [dim]Restart alabs to use the new version[/dim]")
    else:
        console.print(f"  [red]✗ Update failed:[/red]")
        console.print(f"  [dim]{result.stderr.strip()}[/dim]")

    press_any_key()


def handle_tools():
    """Handle extra tools menu."""
    clear()
    show_banner()

    tools_text = """
  [1] Chromium Browser
  [2] VS Code (code-server)
  [3] Zsh + Oh My Zsh
  [4] Docker (rootless)
  [5] Neovim
  [6] GitHub CLI (gh)

  [0] Back
"""

    show_panel(tools_text, title="Extra Tools", style="magenta")

    console.print()
    choice = read_input("  Select tools to install: ")

    if choice == "0":
        return

    # TODO: Implement tool installation
    console.print("\n[yellow]Tool installation coming soon![/yellow]")
    press_any_key()


def handle_status():
    """Handle status display."""
    clear()
    show_banner()

    # Check container
    container_exists = os.path.exists(PROOT_DIR)
    running = is_running()
    gpu = detect_gpu()

    status_text = f"""
  Container:  {"✓ Installed" if container_exists else "✗ Not found"}
  Desktop:    {"● Running" if running else "○ Not running"}
  GPU:        {get_gpu_summary(gpu)}
  Version:    {get_version()}
"""

    show_panel(status_text, title="System Status", style="cyan")
    press_any_key()


def handle_uninstall():
    """Handle uninstall."""
    clear()
    show_banner()

    console.print("\n[bold red]⚠ This will remove arinanoLabs completely![/bold red]")
    console.print("  • Debian container")
    console.print("  • Launcher scripts")
    console.print("  • Config files\n")

    confirm = read_input("  Type 'yes' to confirm: ")
    if confirm != "yes":
        console.print("\n[dim]Uninstall cancelled.[/dim]")
        press_any_key()
        return

    # TODO: Implement uninstall
    console.print("\n[yellow]Uninstall coming soon![/yellow]")
    press_any_key()


if __name__ == "__main__":
    main()
