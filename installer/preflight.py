"""Pre-flight checks before install."""

import os
import socket
import shutil
import subprocess
from typing import NamedTuple

from .ui import console, run_cmd, PROOT_DIR


class CheckResult(NamedTuple):
    name: str
    ok: bool
    message: str


def check_internet() -> CheckResult:
    """Check internet connectivity via TCP socket."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return CheckResult("Internet", True, "Connected")
    except (OSError, socket.timeout):
        return CheckResult("Internet", False, "No connection")


def check_storage(min_gb: float = 2.0) -> CheckResult:
    """Check available storage."""
    try:
        free_bytes = shutil.disk_usage("/data").free
        free_gb = free_bytes / (1024 ** 3)
        if free_gb >= min_gb:
            return CheckResult("Storage", True, f"{free_gb:.1f} GB free")
        else:
            return CheckResult("Storage", False, f"{free_gb:.1f} GB free (need {min_gb} GB)")
    except Exception:
        return CheckResult("Storage", False, "Cannot check storage")


def check_python() -> CheckResult:
    """Check Python is available."""
    version = sys.version.split()[0]
    return CheckResult("Python", True, f"v{version}")


def check_proot() -> CheckResult:
    """Check proot-distro is installed."""
    rc, output = run_cmd("command -v proot-distro")
    if rc == 0:
        return CheckResult("proot-distro", True, "Installed")
    else:
        return CheckResult("proot-distro", False, "Not installed (will install)")


def check_termux_api() -> CheckResult:
    """Check Termux:X11 is available."""
    rc, _ = run_cmd("command -v termux-x11")
    if rc == 0:
        return CheckResult("Termux:X11", True, "Installed")
    else:
        return CheckResult("Termux:X11", False, "Not installed (will install)")


def check_already_installed() -> CheckResult:
    """Check if arinanoLabs container already exists."""
    if os.path.exists(PROOT_DIR):
        return CheckResult("Container", True, "Already installed")
    else:
        return CheckResult("Container", False, "Not installed")


def run_all_checks() -> list[CheckResult]:
    """Run all pre-flight checks."""
    checks = [
        check_internet(),
        check_storage(),
        check_python(),
        check_proot(),
        check_termux_api(),
    ]
    return checks


def print_checks(checks: list[CheckResult]):
    """Print check results."""
    for i, check in enumerate(checks, 1):
        icon = "[green]✓[/green]" if check.ok else "[red]✗[/red]"
        console.print(f"  [{i}/{len(checks)}] {icon} {check.name}: {check.message}")


def all_passed(checks: list[CheckResult]) -> bool:
    """Check if all critical checks passed."""
    # Internet is critical, others are warnings
    return any(c.name == "Internet" and not c.ok for c in checks)


# Needed for sys import
import sys
