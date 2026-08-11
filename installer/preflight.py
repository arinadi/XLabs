"""Environment checks.

Pure stdlib on purpose: the installer runs these before anything has been
pip-installed, so this module must not import textual, rich, or system.py.
"""

import os
import shutil
import socket
import sys
from typing import NamedTuple

from .const import PROOT_DIR


class CheckResult(NamedTuple):
    name: str
    ok: bool
    message: str


def check_internet() -> CheckResult:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5).close()
        return CheckResult("Internet", True, "Connected")
    except OSError:
        return CheckResult("Internet", False, "No connection")


def check_storage(min_gb: float = 4.0) -> CheckResult:
    """The image unpacks to well over 2 GB, so warn below 4 GB free."""
    for path in ("/data", os.path.expanduser("~"), "/"):
        try:
            free_gb = shutil.disk_usage(path).free / (1024**3)
        except OSError:
            continue
        ok = free_gb >= min_gb
        detail = f"{free_gb:.1f} GB free"
        return CheckResult("Storage", ok, detail if ok else f"{detail} (need {min_gb:g} GB)")
    return CheckResult("Storage", False, "Cannot determine free space")


def check_python() -> CheckResult:
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 9)
    version = f"v{major}.{minor}"
    return CheckResult("Python", ok, version if ok else f"{version} (need 3.9+)")


def check_proot() -> CheckResult:
    found = shutil.which("proot-distro") is not None
    return CheckResult("proot-distro", found, "Installed" if found else "Missing")


def check_x11() -> CheckResult:
    found = shutil.which("termux-x11") is not None
    return CheckResult("Termux:X11", found, "Installed" if found else "Missing")


def check_container() -> CheckResult:
    found = os.path.isdir(os.path.join(PROOT_DIR, "rootfs"))
    return CheckResult("Container", found, "Installed" if found else "Not installed")


def run_all_checks() -> list[CheckResult]:
    return [
        check_internet(),
        check_storage(),
        check_python(),
        check_proot(),
        check_x11(),
        check_container(),
    ]


def blocking_failure(checks: list[CheckResult]) -> CheckResult | None:
    """Return the first check that must pass before installing, if it failed.

    Only Internet is fatal — the rest describe work the installer is about
    to do anyway.
    """
    for check in checks:
        if check.name == "Internet" and not check.ok:
            return check
    return None
