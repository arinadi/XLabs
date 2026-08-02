"""Simple TUI for arinanoLabs — input-based, guaranteed to work."""

import os
import sys


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def show_menu():
    from .ui import get_version
    clear()
    print()
    print(f"  📱 arinanoLabs v{get_version()}")
    print()
    print("  Main Menu")
    print()
    print("  1  ▶️  Start Desktop")
    print("  2  ⏹️  Stop Desktop")
    print("  3  🔄  Update")
    print("  4  🧰  Extra Tools")
    print("  5  📊  Status")
    print()
    print("  0  🚪  Exit")
    print()


def handle_start():
    clear()
    print()
    print("  ▶️  Starting desktop...")
    print()
    from .start import start_desktop
    success = start_desktop()
    print()
    if success:
        print("  ✓ Desktop started!")
        print("  Open Termux:X11 app to see your desktop.")
    else:
        print("  ✗ Failed to start desktop")
    print()
    input("  Press Enter to go back...")


def handle_stop():
    clear()
    print()
    print("  ⏹️  Stopping desktop...")
    print()
    from .start import stop_desktop
    stop_desktop()
    print("  ✓ Desktop stopped")
    print()
    input("  Press Enter to go back...")


def handle_update():
    import subprocess
    clear()
    print()
    print("  🔄  Updating...")
    print()

    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if not os.path.exists(os.path.join(repo_dir, ".git")):
        print("  ✗ Not a git repository")
        print("  Reinstall via install.sh")
        print()
        input("  Press Enter to go back...")
        return

    print("  → Pulling latest changes...")
    result = subprocess.run(["git", "pull"], cwd=repo_dir, capture_output=True, text=True)

    if result.returncode != 0:
        print("  → Fetching latest...")
        subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_dir, capture_output=True)
        result = subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=repo_dir, capture_output=True, text=True)

    if result.returncode == 0:
        if "Already up to date" in result.stdout:
            print("  ✓ Already on latest version")
        else:
            print("  ✓ Updated! Restarting...")
            print()
            # Find the script that launched us
            launcher = os.path.expanduser("~/.local/bin/alabs")
            if os.path.exists(launcher):
                os.execl("/bin/bash", "bash", launcher)
            else:
                os.execl(sys.executable, sys.executable, *sys.argv)
    else:
        print("  ✗ Update failed")

    print()
    input("  Press Enter to go back...")


def handle_tools():
    clear()
    print()
    print("  🧰  Extra Tools")
    print()
    print("  [1] Chromium Browser")
    print("  [2] VS Code (code-server)")
    print("  [3] Zsh + Oh My Zsh")
    print("  [4] Neovim")
    print("  [5] GitHub CLI")
    print()
    print("  Coming soon!")
    print()
    input("  Press Enter to go back...")


def handle_status():
    from .start import is_running
    from .ui import is_installed, get_version
    from .gpu import detect_gpu, get_gpu_summary

    clear()
    print()
    print("  📊  System Status")
    print()

    container = is_installed()
    running = is_running()
    gpu = detect_gpu()

    print(f"  Container:  {'✓ Installed' if container else '✗ Not found'}")
    print(f"  Desktop:    {'● Running' if running else '○ Not running'}")
    print(f"  GPU:        {get_gpu_summary(gpu)}")
    print(f"  Version:    {get_version()}")
    print()
    input("  Press Enter to go back...")


def run_npyscreen():
    """Run the TUI — simple input-based, no fancy widgets."""
    while True:
        show_menu()
        choice = input("  Select: ").strip()

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
        elif choice == "0":
            clear()
            print()
            print("  Goodbye! 👋")
            print()
            break
        else:
            print()
            print("  Invalid option. Try again.")
            print()
            input("  Press Enter...")
