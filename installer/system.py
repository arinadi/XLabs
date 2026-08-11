"""Subprocess and filesystem helpers.

Everything here blocks. Call it from a Textual thread worker, never from the
event loop.
"""

import os
import shutil
import signal
import subprocess
import threading
from datetime import datetime, timezone

from .const import HOME_BIN, LAUNCHER_SRC, PREFIX_BIN, PROOT_DIR, REPO_DIR


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


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the command and everything it spawned.

    proc.kill() only reaches the shell started by shell=True. Its children
    keep running and keep the stdout pipe open, so the reader never sees EOF
    and a timeout has no effect — which is exactly how the watchdog here
    failed the first time.
    """
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        proc.kill()


def stream_cmd(cmd: str, log, timeout: int = 900) -> int:
    """Run a shell command, sending each output line to `log`.

    Returns the exit code, or 1 if the command outran `timeout`.

    The deadline is enforced by a watchdog timer rather than checked while
    reading output. A stalled download produces no lines at all, so a
    per-line check never fires — which left every long operation here with
    no working timeout.
    """
    proc = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        errors="replace",
        # Own process group, so the whole tree can be killed at once.
        start_new_session=os.name != "nt",
    )

    timed_out = threading.Event()

    def _expire() -> None:
        timed_out.set()
        _kill_tree(proc)

    watchdog = threading.Timer(timeout, _expire)
    watchdog.start()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            log(line.rstrip())
        rc = proc.wait()
    finally:
        watchdog.cancel()

    if timed_out.is_set():
        log(f"[red]Timed out after {timeout}s[/red]")
        return 1
    return rc


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


def link_launcher() -> tuple[bool, str]:
    """Put `alabs` on PATH. Returns (ok, message).

    Prefers $PREFIX/bin because that is Termux's entire default PATH — no
    shell startup file has to be edited, and the command works immediately in
    the session that ran the installer. Falls back to ~/bin elsewhere.
    """
    if not os.path.exists(LAUNCHER_SRC):
        return False, f"{LAUNCHER_SRC} not found"

    try:
        os.chmod(LAUNCHER_SRC, 0o755)
    except OSError:
        pass

    for directory in (PREFIX_BIN, HOME_BIN):
        # Only create ~/bin; a missing $PREFIX/bin means this is not Termux.
        if directory == PREFIX_BIN and not os.path.isdir(directory):
            continue
        try:
            os.makedirs(directory, exist_ok=True)
            link = os.path.join(directory, "alabs")
            if os.path.islink(link) or os.path.exists(link):
                os.remove(link)
            try:
                os.symlink(LAUNCHER_SRC, link)
            except OSError:
                # Some filesystems reject symlinks; a copy still works, it
                # just needs re-linking after an update.
                shutil.copy2(LAUNCHER_SRC, link)
                os.chmod(link, 0o755)
            return True, link
        except OSError:
            continue

    return False, "no writable directory on PATH"


def ensure_home_bin_on_path() -> list[str]:
    """Add ~/bin to PATH in both login and interactive startup files.

    Only needed on the ~/bin fallback. Termux starts shells through `login`,
    so .bashrc alone is not enough — bash reads .profile for login shells.
    """
    touched = []
    for rc in (os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.profile")):
        try:
            existing = open(rc).read() if os.path.exists(rc) else ""
        except OSError:
            continue
        if "$HOME/bin" in existing:
            continue
        try:
            with open(rc, "a") as f:
                f.write('\n# arinanoLabs\nexport PATH="$HOME/bin:$PATH"\n')
            touched.append(rc)
        except OSError:
            continue
    return touched


def human_size(path: str) -> str:
    """Human-readable size of a directory tree, or '-' if absent."""
    if not os.path.exists(path):
        return "-"
    rc, out = run_cmd(f"du -sh {path} 2>/dev/null")
    if rc == 0 and out.strip():
        return out.split()[0]
    return "unknown"
