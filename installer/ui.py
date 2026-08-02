"""Shared UI components for arinanoLabs TUI."""

import os
import sys
import subprocess
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.live import Live
from rich.align import Align

console = Console(force_terminal=True)

# ── Constants ──────────────────────────────────────────────
PROOT_DIR = "/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs"


def clear():
    """Clear terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def is_installed() -> bool:
    """Check if arinanoLabs is installed (proot container exists)."""
    return os.path.exists(PROOT_DIR)


def get_version() -> str:
    """Get version as date.hash."""
    from datetime import datetime, timezone
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        git_hash = result.stdout.strip() if result.returncode == 0 else "unknown"
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{date_str}.{git_hash}"
    except Exception:
        return "unknown"


def run_cmd(cmd: str, timeout: int = 60) -> tuple[int, str]:
    """Run shell command and return (returncode, output)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 1, "Command timed out"
    except Exception as e:
        return 1, str(e)


def run_cmd_stream(cmd: str, callback=None):
    """Run command and stream output line by line."""
    process = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    for line in process.stdout:
        if callback:
            callback(line.strip())
        else:
            print(line.strip())
    process.wait()
    return process.returncode


# ── UI Components ──────────────────────────────────────────

def show_banner():
    """Show arinanoLabs banner."""
    banner = Text()
    banner.append("📱 arinanoLabs", style="bold cyan")
    banner.append(f" v{get_version()}", style="dim")
    console.print(Align.center(banner))


def show_panel(content: str, title: str = "", style: str = "blue"):
    """Show content in a panel."""
    console.print(Panel(content, title=title, style=style, expand=False))


def show_status_line(label: str, value: str, ok: bool = True):
    """Show a status line with checkmark or X."""
    icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
    console.print(f"  {icon} {label}: {value}")


def show_progress_download(description: str, total: int, iterator):
    """Show progress bar for download."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(description, total=total)
        for data in iterator:
            yield data
            progress.advance(task, len(data) if hasattr(data, '__len__') else 1)


def read_input(prompt: str) -> str:
    """Read input, handling piped stdin (curl | bash)."""
    if not sys.stdin.isatty():
        return ""
    return input(prompt).strip()


def confirm_action(message: str) -> bool:
    """Ask user for confirmation."""
    console.print(f"\n{message}")
    response = read_input("  Continue? [y/N] ").lower()
    return response in ("y", "yes")


def press_any_key():
    """Wait for user to press any key."""
    console.print("\n  [dim]Press any key to return...[/dim]")
    if sys.stdin.isatty():
        input()


def show_error(message: str):
    """Show error message."""
    console.print(f"\n[red]✗ {message}[/red]")


def show_success(message: str):
    """Show success message."""
    console.print(f"\n[green]✓ {message}[/green]")


def show_warning(message: str):
    """Show warning message."""
    console.print(f"\n[yellow]⚠ {message}[/yellow]")
