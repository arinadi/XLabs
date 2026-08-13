"""Termux packages the container already provides.

proot-distro binds Termux's $PREFIX into the container and appends it to the
guest's PATH, so Termux binaries are reachable inside by design. Because it
appends, a tool present in both resolves to the Debian copy — the Termux one
only surfaces when Debian lacks it, which is exactly when it is confusing.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from .system import container_command, is_installed, run_cmd, stream_cmd, write_container_script

Log = Callable[[str], None]

# Only these are ever offered for removal, and only after the container is
# confirmed to provide the tool. Everything XLabs itself runs on —
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
    if not write_container_script("xlabs-which.sh", script):
        return set()

    rc, out = run_cmd(
        container_command("xlabs-which.sh"),
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
