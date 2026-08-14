"""Claude Code's global memory file: ~/.claude/CLAUDE.md inside the
container, loaded by Claude Code at the start of every session regardless of
which project is open.

Plain text, no parsing — unlike providers.py/mcp_manager.py this isn't JSON,
just prose read back and written out as-is.
"""

from __future__ import annotations

import os
from typing import Callable

from .const import ADMIN_USER
from .system import container_path

Log = Callable[[str], None]

CLAUDE_MD_REL = f"/home/{ADMIN_USER}/.claude/CLAUDE.md"


def _path() -> str:
    return container_path(CLAUDE_MD_REL)


def read() -> str:
    try:
        with open(_path(), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def write(content: str, log: Log) -> bool:
    path = _path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    except OSError as e:
        log(f"[red]Could not write {CLAUDE_MD_REL}: {e}[/red]")
        return False
    log(f"{CLAUDE_MD_REL} saved.")
    return True
