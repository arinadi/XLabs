"""arinaLabs TUI — simple, works everywhere."""

import os
import sys


def run_npyscreen():
    """Run TUI — just input() calls, no libraries."""
    while True:
        # Get version from git
        try:
            import subprocess
            r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            git_hash = r.stdout.strip() if r.returncode == 0 else "unknown"
        except Exception:
            git_hash = "unknown"

        from datetime import datetime, timezone
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        version = f"{date_str}.{git_hash}"

        os.system("cls" if os.name == "nt" else "clear")
        print()
        print(f"  arinanoLabs v{version}")
        print()
        print("  1  Start Desktop")
        print("  2  Stop Desktop")
        print("  3  Update")
        print("  4  Extra Tools")
        print("  5  Status")
        print("  0  Exit")
        print()

        choice = input("  Select: ").strip()

        if choice == "1":
            _start_desktop()
        elif choice == "2":
            _stop_desktop()
        elif choice == "3":
            _update()
        elif choice == "4":
            _tools()
        elif choice == "5":
            _status()
        elif choice == "0":
            os.system("cls" if os.name == "nt" else "clear")
            print("\n  Goodbye!\n")
            break


def _start_desktop():
    os.system("cls" if os.name == "nt" else "clear")
    print("\n  Starting desktop...\n")
    from .start import start_desktop
    if start_desktop():
        print("  Desktop started!")
        print("  Open Termux:X11 app to see your desktop.")
    else:
        print("  Failed to start desktop")
    input("\n  Press Enter...")


def _stop_desktop():
    os.system("cls" if os.name == "nt" else "clear")
    print("\n  Stopping desktop...\n")
    from .start import stop_desktop
    stop_desktop()
    print("  Desktop stopped")
    input("\n  Press Enter...")


def _update():
    import subprocess
    os.system("cls" if os.name == "nt" else "clear")
    print("\n  Updating...\n")

    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(os.path.join(repo_dir, ".git")):
        print("  Not a git repository")
        input("\n  Press Enter...")
        return

    print("  Pulling latest changes...")
    result = subprocess.run(["git", "pull"], cwd=repo_dir, capture_output=True, text=True)

    if result.returncode != 0:
        print("  Fetching latest...")
        subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_dir, capture_output=True)
        result = subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=repo_dir, capture_output=True, text=True)

    if result.returncode == 0:
        if "Already up to date" in result.stdout:
            print("  Already on latest version")
        else:
            print("  Updated!")
            print("  Restart alabs to use new version")
    else:
        print("  Update failed")

    input("\n  Press Enter...")


def _tools():
    os.system("cls" if os.name == "nt" else "clear")
    print("\n  Extra Tools\n")
    print("  1  Chromium Browser")
    print("  2  VS Code (code-server)")
    print("  3  Zsh + Oh My Zsh")
    print("  4  Neovim")
    print("  5  GitHub CLI")
    print("\n  Coming soon!")
    input("\n  Press Enter...")


def _status():
    from .start import is_running
    from .ui import is_installed
    from .gpu import detect_gpu, get_gpu_summary

    os.system("cls" if os.name == "nt" else "clear")
    print("\n  System Status\n")

    container = is_installed()
    running = is_running()
    gpu = detect_gpu()

    print(f"  Container:  {'Installed' if container else 'Not found'}")
    print(f"  Desktop:    {'Running' if running else 'Not running'}")
    print(f"  GPU:        {get_gpu_summary(gpu)}")
    input("\n  Press Enter...")
