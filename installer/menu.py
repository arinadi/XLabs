"""Main TUI menu for arinanoLabs."""

import os
import sys
import select
import termios
import tty

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


# ── Mouse Support ──────────────────────────────────────────

def _enable_mouse():
    """Enable mouse tracking in terminal."""
    sys.stdout.write("\033[?1003h\033[?1006h")  # Track all mouse movement + SGR mode
    sys.stdout.flush()


def _disable_mouse():
    """Disable mouse tracking."""
    sys.stdout.write("\033[?1003l\033[?1006l")
    sys.stdout.flush()


def _read_mouse_event():
    """Read mouse event from stdin. Returns (x, y, pressed) or None."""
    if not sys.stdin.isatty():
        return None

    # Non-blocking read
    if select.select([sys.stdin], [], [], 0.1)[0]:
        data = sys.stdin.read(20)  # Read enough for mouse escape sequence

        # SGR mouse format: ESC [ < Cb ; Cx ; Cy M/m
        if "\033[<" in data:
            try:
                params = data.split("M")[0].split("m")[0]
                parts = params.replace("\033[<", "").split(";")
                if len(parts) >= 3:
                    cb = int(parts[0])  # button
                    cx = int(parts[1])  # column
                    cy = int(parts[2])  # row
                    pressed = "M" in data  # M=press, m=release
                    return (cx, cy, pressed)
            except (ValueError, IndexError):
                pass

    return None


# ── Menu Items (y positions for click detection) ──────────

MENU_ITEMS = {
    1: "start",
    2: "stop",
    3: "update",
    4: "tools",
    5: "status",
    6: "uninstall",
    0: "exit",
}


def run_installed_menu():
    """Run main menu when already installed."""
    _enable_mouse()
    try:
        while True:
            clear()
            show_banner()

            console.print()
            console.print("  [bold]Main Menu[/bold]")
            console.print()
            console.print("  [cyan]1[/cyan]  ▶️  Start Desktop")
            console.print("  [cyan]2[/cyan]  ⏹️  Stop Desktop")
            console.print("  [cyan]3[/cyan]  🔄  Update")
            console.print("  [cyan]4[/cyan]  🧰  Extra Tools")
            console.print("  [cyan]5[/cyan]  📊  Status")
            console.print("  [cyan]6[/cyan]  🗑️   Uninstall")
            console.print()
            console.print("  [dim]0  🚪  Exit[/dim]")
            console.print()
            console.print("  [dim]Click or type to select:[/dim]")
            console.print()

            choice = _get_choice_with_mouse()

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
    finally:
        _disable_mouse()


def _get_choice_with_mouse() -> str:
    """Get menu choice via keyboard or mouse click."""
    if not sys.stdin.isatty():
        return read_input("  Select option: ")

    # Reset terminal state
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)

        while True:
            event = _read_mouse_event()
            if event:
                cx, cy, pressed = event
                if pressed:
                    # Map y position to menu item (approximate)
                    # Panel starts at some y, items are spaced
                    # This is a rough mapping — adjust based on actual layout
                    return _map_click_to_choice(cy)

            # Also check for keyboard input
            if select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch in ("\n", "\r"):
                    return ""
                elif ch.isdigit():
                    return ch
                elif ch == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt()
                elif ch == "\x04":  # Ctrl+D
                    return "0"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _map_click_to_choice(y: int) -> str:
    """Map terminal y-coordinate to menu choice."""
    # Menu layout (approximate y positions):
    # Banner: ~3 lines
    # Panel border: 1 line
    # [1] Start: +2
    # [2] Stop: +1
    # [3] Update: +1
    # [4] Tools: +1
    # [5] Status: +1
    # [6] Uninstall: +1
    # Panel border: 1 line
    #
    # Adjust these offsets based on actual rendering
    menu_start_y = 8  # Approximate y where [1] starts

    offset = y - menu_start_y
    if offset == 0:
        return "1"
    elif offset == 1:
        return "2"
    elif offset == 2:
        return "3"
    elif offset == 3:
        return "4"
    elif offset == 4:
        return "5"
    elif offset == 5:
        return "6"
    else:
        return ""


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

    # Normal pull
    result = subprocess.run(
        ["git", "pull"],
        cwd=repo_dir, capture_output=True, text=True
    )

    # If failed, fetch + reset
    if result.returncode != 0:
        console.print("  [dim]Fetching latest...[/dim]")
        subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_dir, capture_output=True)
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
        console.print(f"  [red]✗ Update failed[/red]")

    press_any_key()


def handle_tools():
    """Handle extra tools menu."""
    clear()
    show_banner()

    console.print()
    console.print("  [bold]Extra Tools[/bold]")
    console.print()
    console.print("  [cyan]1[/cyan]  Chromium Browser")
    console.print("  [cyan]2[/cyan]  VS Code (code-server)")
    console.print("  [cyan]3[/cyan]  Zsh + Oh My Zsh")
    console.print("  [cyan]4[/cyan]  Docker (rootless)")
    console.print("  [cyan]5[/cyan]  Neovim")
    console.print("  [cyan]6[/cyan]  GitHub CLI (gh)")
    console.print()
    console.print("  [dim]0  Back[/dim]")
    console.print()

    choice = read_input("  Select: ")

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

    console.print()
    console.print("  [bold]System Status[/bold]")
    console.print()
    console.print(f"  Container:  {'✓ Installed' if container_exists else '✗ Not found'}")
    console.print(f"  Desktop:    {'● Running' if running else '○ Not running'}")
    console.print(f"  Version:    {get_version()}")
    console.print()
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


def main():
    """Main entry point for TUI."""
    try:
        if is_installed():
            run_installed_menu()
        else:
            run_fresh_install()
    except KeyboardInterrupt:
        _disable_mouse()
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


if __name__ == "__main__":
    main()
