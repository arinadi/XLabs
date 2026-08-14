"""Fonts Doctor can install and activate inside the container.

Validated against issue #6's real-device audit and the research that
followed it, not taken on the audit's word: DejaVu (already installed)
already covers arrows, math, UI symbols, geometric shapes, card suits and
box-drawing — direct glyph inspection confirmed that, contradicting the
audit's "tofu box" claim for those categories. The one real gap is color
emoji, and fonts-noto-color-emoji is the only modern, complete emoji font
Debian packages at all — Twemoji, OpenMoji and JoyPixels aren't in the
Debian repos. Fira Code is a separate, opt-in pick: a monospace font with
programming ligatures, activated as the xfce4-terminal font once
installed — installing it alone would not otherwise change anything, since
nothing points the terminal at it by default.
"""

from __future__ import annotations

import os
from typing import Callable

from .const import ADMIN_USER
from .system import (
    container_command,
    container_path,
    is_installed,
    run_cmd,
    stream_cmd,
    write_container_script,
)

Log = Callable[[str], None]

PACKAGES = ("fonts-noto-color-emoji", "fonts-firacode")

HOME = f"/home/{ADMIN_USER}"
TERMINAL_RC = f"{HOME}/.config/xfce4/terminal/terminalrc"
TERMINAL_FONT = "Fira Code 11"
CONFIG_SECTION = "[Configuration]"

INSTALLED_SCRIPT = """#!/bin/bash
dpkg-query -W -f='${Package}\\n' 2>/dev/null
"""

INSTALL_SCRIPT = f"""#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y {' '.join(PACKAGES)}
fc-cache -f
"""


def _installed_packages() -> set[str]:
    if not write_container_script("xlabs-fonts-installed.sh", INSTALLED_SCRIPT):
        return set()
    rc, out = run_cmd(container_command("xlabs-fonts-installed.sh"), timeout=30)
    return set(out.split()) if rc == 0 else set()


def fonts_installed() -> bool:
    if not is_installed():
        return False
    installed = _installed_packages()
    return all(pkg in installed for pkg in PACKAGES)


def terminal_font_active() -> bool:
    try:
        with open(container_path(TERMINAL_RC), encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return False
    return any(line.strip() == f"FontName={TERMINAL_FONT}" for line in content.splitlines())


def fonts_ready() -> bool:
    return fonts_installed() and terminal_font_active()


def _patch_ini_section(lines: list[str], section: str, updates: dict[str, str]) -> list[str]:
    """Set `updates` inside `section` of an INI-style file, creating the
    section if it is missing. Every other line and section is left as-is —
    xfce4-terminal owns the rest of this file (tab behaviour, colors,
    whatever the user already set), not this module.
    """
    result = list(lines)
    remaining = dict(updates)

    try:
        start = result.index(section)
    except ValueError:
        block = [section] + [f"{k}={v}" for k, v in updates.items()]
        return block + result

    end = start + 1
    while end < len(result) and not result[end].startswith("["):
        key = result[end].split("=", 1)[0] if "=" in result[end] else None
        if key in remaining:
            result[end] = f"{key}={remaining.pop(key)}"
        end += 1

    if remaining:
        result[end:end] = [f"{k}={v}" for k, v in remaining.items()]

    return result


def _activate_terminal_font(log: Log) -> bool:
    target = container_path(TERMINAL_RC)
    try:
        with open(target, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []

    lines = _patch_ini_section(
        lines, CONFIG_SECTION, {"FontName": TERMINAL_FONT, "FontUseSystem": "FALSE"}
    )

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as e:
        log(f"  could not write {TERMINAL_RC}: {e}")
        return False
    return True


def install_and_activate(log: Log) -> bool:
    if not is_installed():
        log("  no container to install into")
        return False

    if not fonts_installed():
        if not write_container_script("xlabs-fonts-install.sh", INSTALL_SCRIPT):
            log("  could not write the install script")
            return False
        if stream_cmd(container_command("xlabs-fonts-install.sh"), log, timeout=300) != 0:
            log("  [red]apt install failed[/red]")
            return False
        log(f"  installed {', '.join(PACKAGES)}, refreshed the font cache")

    if not _activate_terminal_font(log):
        return False
    log(f"  xfce4-terminal font set to {TERMINAL_FONT}")
    log("  restart xfce4-terminal for it to take effect")
    return True
