"""Self-healing Termux mirror fallback."""

import os
from .ui import run_cmd, console


# ── Mirror List ────────────────────────────────────────────

MIRRORS = [
    "https://packages.termux.dev",
    "https://mirror.mentality.rip/termux",
    "https://termux.mentality.rip",
]

SOURCES_FILE = os.path.expanduser("$PREFIX/etc/apt/sources.list")


def get_current_mirror() -> str:
    """Read current mirror from sources.list."""
    try:
        with open(SOURCES_FILE, "r") as f:
            for line in f:
                if line.strip().startswith("deb"):
                    # Extract URL
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        return parts[1]
    except FileNotFoundError:
        pass
    return "unknown"


def set_mirror(mirror: str):
    """Write mirror to sources.list."""
    sources = f"deb {mirror} termux main\n"
    try:
        os.makedirs(os.path.dirname(SOURCES_FILE), exist_ok=True)
        with open(SOURCES_FILE, "w") as f:
            f.write(sources)
        console.print(f"  [dim]Switched mirror to: {mirror}[/dim]")
    except Exception as e:
        console.print(f"  [red]Failed to set mirror: {e}[/red]")


def test_mirror(mirror: str, timeout: int = 15) -> bool:
    """Test if mirror is reachable."""
    # Write mirror and try pkg update
    set_mirror(mirror)
    rc, _ = run_cmd("pkg update -y 2>/dev/null", timeout=timeout)
    return rc == 0


def ensure_mirror() -> bool:
    """Try mirrors until one works. Returns True if successful."""
    console.print("\n[bold]Checking Termux repositories...[/bold]")

    for i, mirror in enumerate(MIRRORS, 1):
        console.print(f"  [{i}/{len(MIRRORS)}] Trying {mirror}...")
        if test_mirror(mirror):
            console.print(f"  [green]✓ Mirror working: {mirror}[/green]")
            return True

    console.print("\n[red]✗ All mirrors failed. Check your internet connection.[/red]")
    return False


def reset_to_primary():
    """Reset to primary mirror."""
    set_mirror(MIRRORS[0])
