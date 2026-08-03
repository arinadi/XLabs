"""Welcome screen and install detection."""

import os
from .ui import (
    console, clear, read_input, is_installed, get_version, show_banner,
    show_panel, PROOT_DIR
)
from .preflight import run_all_checks, print_checks


def show_welcome():
    """Show welcome screen for fresh install."""
    clear()
    show_banner()

    console.print()
    console.print("  [bold cyan]Debian 13 · Xfce4 · Firefox ESR · Dev tools[/bold cyan]")
    console.print()
    console.print("  ✓ No root required")
    console.print("  ✓ ~30 seconds install")
    console.print("  ✓ Touch-optimized for mobile")
    console.print("  ✓ Auto-configured")
    console.print()
    console.print("  [dim]What you get:[/dim]")
    console.print("  • Xfce4 desktop with on-screen keyboard")
    console.print("  • Firefox ESR browser")
    console.print("  • Node.js 22, Python 3, GCC, CMake")
    console.print("  • HiDPI scaling for tablets")
    console.print()


def show_already_installed():
    """Show menu when already installed."""
    clear()
    show_banner()

    menu_text = """
  [1] ▶️  Start Desktop
  [2] ⏹️  Stop Desktop
  [3] 🔄 Update
  [4] 🧰 Extra Tools
  [5] 📊 Status
  [6] 🗑️  Uninstall

  [0] 🚪 Exit
"""

    show_panel(menu_text, title="Main Menu", style="green")


def get_user_choice() -> str:
    """Get user menu choice."""
    console.print()
    choice = read_input("  Select option: ")
    return choice


def run_preflight():
    """Run pre-flight checks and display results."""
    console.print("\n[bold]Running pre-flight checks...[/bold]\n")

    checks = run_all_checks()
    print_checks(checks)

    # Check internet specifically
    internet_ok = any(c.name == "Internet" and c.ok for c in checks)
    if not internet_ok:
        console.print("\n[red]✗ Internet connection required for installation.[/red]")
        return False

    return True


def show_install_button():
    """Show the install button prompt."""
    console.print()
    console.print("  [bold cyan]Ready to install![/bold cyan]")
    console.print()
    response = read_input("  Press [Enter] to install, or Ctrl+C to cancel... ")
    return response == ""


def show_post_install_info():
    """Show post-install information."""
    clear()
    show_banner()

    info_text = f"""
[bold green]Installation complete![/bold green]

[bold]Quick start:[/bold]
  [cyan]alabs[/cyan]              Launch TUI menu
  [cyan]alabs[/cyan]              Launch TUI menu

[bold]Useful commands:[/bold]
  alabs                  Open main menu
"""

    show_panel(info_text, title="✅ Ready!", style="green")
