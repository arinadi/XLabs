"""Diagnose the Termux environment and repair what can be repaired.

Every issue carries its own fix, so the UI does not need to know how any of
them work — it renders the list and calls `fix(log)` on the ones that have
one. An issue with `fix=None` needs the user; say so in `detail`.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Callable, NamedTuple

from . import start as desktop
from .const import (
    CONTAINER_NAME,
    IMAGE_REF,
    LAUNCHER_SRC,
    PREFIX_BIN,
    REPO_DIR,
    TMPDIR,
)
from .preflight import X11_APK_URL, check_x11_app
from .system import (
    ensure_home_bin_on_path,
    is_installed,
    link_launcher,
    run_cmd,
    stream_cmd,
)

Log = Callable[[str], None]


class Issue(NamedTuple):
    name: str
    ok: bool
    detail: str
    fix: Callable[[Log], bool] | None = None
    # The check could not be performed — not the same as "the thing is absent".
    unknown: bool = False


# ── Fixes ──────────────────────────────────────────────────


def _fix_launcher(log: Log) -> bool:
    linked, where = link_launcher()
    if not linked:
        log(f"  {where}")
        return False
    log(f"  linked {where} -> {LAUNCHER_SRC}")
    if not where.startswith(PREFIX_BIN):
        for rc in ensure_home_bin_on_path():
            log(f"  added ~/bin to PATH in {rc}")
        log("  open a new session for PATH to take effect")
    return True


def _fix_pip(log: Log) -> bool:
    req = os.path.join(REPO_DIR, "requirements.txt")
    target = f"-r {req}" if os.path.exists(req) else "textual"
    # sys.executable, not "python3": on a device with more than one Python the
    # repair would otherwise install into an interpreter the TUI never uses
    # and then report success.
    for flag in ("", " --break-system-packages", " --user"):
        if stream_cmd(
            f'"{sys.executable}" -m pip install {target}{flag}', log, timeout=600
        ) == 0:
            return True
    return False


def _pkg_fix(label: str, packages: list[str], with_x11_repo: bool = False):
    def fix(log: Log) -> bool:
        if with_x11_repo:
            log(f"  enabling x11-repo first ({label} lives there)")
            if stream_cmd("pkg install -y x11-repo", log, timeout=600) != 0:
                return False
            stream_cmd("pkg update -y", log, timeout=600)
        return stream_cmd(f"pkg install -y {' '.join(packages)}", log, timeout=900) == 0

    return fix


def _fix_container(log: Log) -> bool:
    log(f"  pulling {IMAGE_REF} — this takes a few minutes")
    rc = stream_cmd(
        f"proot-distro install {IMAGE_REF} --name {CONTAINER_NAME}", log, timeout=1800
    )
    return rc == 0 and is_installed()


def _fix_stale_sockets(log: Log) -> bool:
    for path in (f"{TMPDIR}/.X11-unix", f"{TMPDIR}/.X*-lock"):
        run_cmd(f"rm -rf {path} 2>/dev/null")
        log(f"  removed {path}")
    return True


# ── Diagnosis ──────────────────────────────────────────────


def _stale_sockets_present() -> bool:
    """X11 leftovers with nothing running to own them.

    A stale .X0-lock is the usual reason a restart fails with the server
    claiming display :0 is already in use.
    """
    if desktop.is_running():
        return False
    rc, _ = run_cmd("pgrep -f termux-x11")
    if rc == 0:
        return False
    if os.path.exists(f"{TMPDIR}/.X11-unix/X0"):
        return True
    return any(
        name.startswith(".X") and name.endswith("-lock")
        for name in (os.listdir(TMPDIR) if os.path.isdir(TMPDIR) else [])
    )


def diagnose() -> list[Issue]:
    issues: list[Issue] = []

    # Repo — nothing else can be fixed without it.
    repo_ok = os.path.isdir(os.path.join(REPO_DIR, ".git"))
    issues.append(
        Issue(
            "Repository",
            repo_ok,
            REPO_DIR if repo_ok else f"{REPO_DIR} is not a git checkout — re-run install.sh",
        )
    )

    # Launcher on PATH.
    found = shutil.which("alabs")
    if found:
        target = os.path.realpath(found)
        correct = target == os.path.realpath(LAUNCHER_SRC)
        issues.append(
            Issue(
                "Launcher",
                correct,
                found if correct else f"{found} points at {target}",
                None if correct else _fix_launcher,
            )
        )
    else:
        issues.append(
            Issue("Launcher", False, "alabs is not on PATH", _fix_launcher)
        )

    # Python libraries.
    try:
        import textual  # noqa: F401

        issues.append(Issue("Textual", True, "Installed"))
    except ImportError:
        issues.append(Issue("Textual", False, "Not installed", _fix_pip))

    # Termux packages.
    for name, binary, packages, x11 in (
        ("proot-distro", "proot-distro", ["proot-distro"], False),
        ("PulseAudio", "pulseaudio", ["pulseaudio"], False),
        ("Termux:X11", "termux-x11", ["termux-x11-nightly", "xorg-xrandr"], True),
    ):
        present = shutil.which(binary) is not None
        issues.append(
            Issue(
                name,
                present,
                "Installed" if present else "Missing",
                None if present else _pkg_fix(name, packages, x11),
            )
        )

    # The Android app cannot be installed from here.
    app = check_x11_app()
    if app.ok:
        detail = app.message
    elif app.unknown:
        detail = f"{app.message} — if the desktop shows, it is installed"
    else:
        detail = f"Missing — sideload from {X11_APK_URL}"
    issues.append(Issue("X11 app", app.ok, detail, unknown=app.unknown))

    # Container.
    container = is_installed()
    issues.append(
        Issue(
            "Container",
            container,
            "Installed" if container else "Not installed",
            None if container else _fix_container,
        )
    )

    # Leftovers from a bad shutdown.
    stale = _stale_sockets_present()
    issues.append(
        Issue(
            "X11 sockets",
            not stale,
            "Stale lock or socket with nothing running" if stale else "Clean",
            _fix_stale_sockets if stale else None,
        )
    )

    return issues


# ── Termux packages the container already provides ─────────

# proot-distro binds the Termux $PREFIX into the container and appends
# $PREFIX/bin to the guest's PATH, so Termux binaries are reachable inside by
# design. Because it appends, a tool present in both resolves to the Debian
# copy — the Termux one only surfaces when Debian lacks it, which is exactly
# when it is confusing.
#
# Only these are ever offered for removal, and only after the container is
# confirmed to provide the tool. Everything arinanoLabs itself runs on —
# python, git, proot-distro, termux-x11-nightly, pulseaudio, the graphics
# packages — is absent from this list on purpose and must stay that way.
TERMUX_DUPLICATES = {
    "nodejs": "node",
    "nodejs-lts": "node",
    "clang": "clang",
    "cmake": "cmake",
    "make": "make",
    "golang": "go",
    "rust": "rustc",
    "ripgrep": "rg",
    "fzf": "fzf",
    "bat": "bat",
    "lazygit": "lazygit",
    "neovim": "nvim",
    "zsh": "zsh",
    "htop": "htop",
    "tmux": "tmux",
}


class Duplicate(NamedTuple):
    package: str
    binary: str


def _installed_termux_packages() -> set[str]:
    rc, out = run_cmd("dpkg-query -W -f='${Package}\\n' 2>/dev/null")
    if rc != 0:
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def _container_provides(binaries: set[str]) -> set[str]:
    """Which of `binaries` the container can actually run."""
    if not binaries:
        return set()

    script = "#!/bin/bash\n" + "".join(
        f'command -v {b} >/dev/null 2>&1 && echo {b}\n' for b in sorted(binaries)
    )
    if not desktop.write_container_script("arinanolabs-which.sh", script):
        return set()

    rc, out = run_cmd(
        f"proot-distro login {CONTAINER_NAME} -- bash /tmp/arinanolabs-which.sh",
        timeout=120,
    )
    if rc != 0:
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def termux_duplicates() -> list[Duplicate]:
    """Termux packages whose job the container already does.

    Returns nothing unless the container exists — without it there is no
    "primary" to defer to, and removing anything would just take the tool away.
    """
    if not is_installed():
        return []

    installed = _installed_termux_packages() & set(TERMUX_DUPLICATES)
    if not installed:
        return []

    wanted = {TERMUX_DUPLICATES[pkg] for pkg in installed}
    provided = _container_provides(wanted)

    return sorted(
        (
            Duplicate(pkg, TERMUX_DUPLICATES[pkg])
            for pkg in installed
            if TERMUX_DUPLICATES[pkg] in provided
        ),
        key=lambda d: d.package,
    )


def remove_termux_packages(packages: list[str], log: Log) -> bool:
    """Remove Termux packages. Refuses anything not on the candidate list."""
    unknown = [p for p in packages if p not in TERMUX_DUPLICATES]
    if unknown:
        log(f"[red]Refusing to remove packages outside the candidate list: {unknown}[/red]")
        return False
    if not packages:
        log("Nothing to remove.")
        return True

    log(f"Removing from Termux: {', '.join(packages)}")
    log("[dim]The container keeps its own copies.[/dim]")
    log("")
    return stream_cmd(f"pkg uninstall -y {' '.join(packages)}", log, timeout=900) == 0


def fixable(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if not i.ok and i.fix is not None]


def run_fixes(issues: list[Issue], log: Log) -> tuple[int, int]:
    """Apply every available fix. Returns (repaired, attempted)."""
    targets = fixable(issues)
    if not targets:
        log("Nothing to fix.")
        return 0, 0

    repaired = 0
    for issue in targets:
        log(f"[bold]{issue.name}[/bold] — {issue.detail}")
        try:
            assert issue.fix is not None
            if issue.fix(log):
                log("  [green]repaired[/green]")
                repaired += 1
            else:
                log("  [red]could not repair[/red]")
        except Exception as e:  # noqa: BLE001
            log(f"  [red]error: {e}[/red]")
        log("")

    return repaired, len(targets)
