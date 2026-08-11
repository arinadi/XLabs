"""Subprocess and filesystem helpers.

Everything here blocks. Call it from a Textual thread worker, never from the
event loop.
"""

import os
import subprocess
from datetime import datetime, timezone

from .const import PROOT_DIR, REPO_DIR


def run_cmd(cmd: str, timeout: int = 60) -> tuple[int, str]:
    """Run a shell command, returning (returncode, combined output)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 1, f"Command timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001 - surfaced to the user as log text
        return 1, str(e)


def stream_cmd(cmd: str, log, timeout: int = 900) -> int:
    """Run a shell command, sending each output line to `log`.

    Returns the exit code, or 1 if the command outran `timeout`.
    """
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        errors="replace",
    )

    deadline = datetime.now(timezone.utc).timestamp() + timeout
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip())
        if datetime.now(timezone.utc).timestamp() > deadline:
            proc.kill()
            log(f"[red]Timed out after {timeout}s[/red]")
            return 1

    return proc.wait()


def is_installed() -> bool:
    """True when the proot container rootfs exists."""
    return os.path.isdir(os.path.join(PROOT_DIR, "rootfs"))


def get_version() -> str:
    """Version string as YYYYMMDD.<short sha>."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_DIR if os.path.isdir(REPO_DIR) else None,
            capture_output=True,
            text=True,
            timeout=5,
        )
        sha = result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:  # noqa: BLE001
        sha = "unknown"
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d')}.{sha}"


def human_size(path: str) -> str:
    """Human-readable size of a directory tree, or '-' if absent."""
    if not os.path.exists(path):
        return "-"
    rc, out = run_cmd(f"du -sh {path} 2>/dev/null")
    if rc == 0 and out.strip():
        return out.split()[0]
    return "unknown"
