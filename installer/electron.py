"""Electron's SUID sandbox needs either a real setuid-root helper or working
unprivileged user namespaces. proot fakes namespace syscalls without a
kernel behind them, so Chromium's zygote sandbox init fails outright and the
app never opens — this is why VS Code (and anything else built on Electron)
does nothing when launched under proot. --no-sandbox turns that subsystem
off; proot is already the outer isolation boundary on a personal device, so
there is nothing behind it worth protecting.

Detected the way distro packagers detect it: a chrome-sandbox helper next to
the resolved binary means Chromium/Electron, whatever the app is — this
catches whatever gets installed later, not only the vscode repo. Chromium
itself is also caught here, so by the time browser.py checks Chromium's own
tuning, --no-sandbox is normally already in place; browser.py adds it itself
too, so it does not depend on this fix having run first.
"""

from __future__ import annotations

import os
from typing import Callable

from . import desktopfiles
from .system import container_path

Log = Callable[[str], None]

NO_SANDBOX = "--no-sandbox"


def electron_desktop_files() -> list[tuple[str, str]]:
    """(path, content) for every .desktop file that launches an Electron app."""
    root = container_path("/")
    found = []
    for path, content in desktopfiles.list_desktop_files(root):
        binary = desktopfiles.desktop_exec_binary(content)
        if not binary:
            continue
        resolved = desktopfiles.find_in_path(root, binary)
        if not resolved:
            continue
        if os.path.isfile(os.path.join(os.path.dirname(resolved), "chrome-sandbox")):
            found.append((path, content))
    return found


def electron_status() -> tuple[int, int]:
    """(Electron apps found, still missing --no-sandbox)."""
    files = electron_desktop_files()
    missing = sum(
        1 for _, content in files if not desktopfiles.desktop_exec_has(content, NO_SANDBOX)
    )
    return len(files), missing


def fix_electron_sandbox(log: Log) -> bool:
    files = electron_desktop_files()
    patched = 0
    ok = True
    for path, content in files:
        if desktopfiles.desktop_exec_has(content, NO_SANDBOX):
            continue
        binary = desktopfiles.desktop_exec_binary(content)
        assert binary is not None
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(desktopfiles.patch_desktop_exec(content, binary, NO_SANDBOX))
        except OSError as e:
            log(f"  could not write {path}: {e}")
            ok = False
            continue
        log(f"  {os.path.basename(path)} -> Exec gets --no-sandbox")
        patched += 1
    log(f"  {patched} of {len(files)} Electron app(s) patched")
    return ok
