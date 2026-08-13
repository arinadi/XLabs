"""Resolve and patch .desktop files inside the container's rootfs.

Shared by electron.py (the Electron/VS Code sandbox patch) and browser.py
(Chromium's own launch flags) — both need to find a .desktop entry's real
binary and edit its Exec= line, so that resolution logic lives once rather
than twice.
"""

from __future__ import annotations

import os

APPLICATIONS_DIR = "/usr/share/applications"
DEFAULT_PATH_DIRS = ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin")


def resolve_in_root(root: str, path: str, depth: int = 0) -> str | None:
    """Host path for `path` as the container itself would resolve it.

    os.path.realpath cannot be used here: an absolute symlink target stored
    inside the container (e.g. /usr/bin/code -> /usr/share/code/code) is only
    absolute *inside the container* — resolved against the host root it
    points somewhere that does not exist.
    """
    if depth > 20:
        return None
    if not path.startswith("/"):
        path = "/" + path
    host = os.path.join(root, path.lstrip("/"))
    if os.path.islink(host):
        target = os.readlink(host)
        if not os.path.isabs(target):
            target = os.path.normpath(os.path.join(os.path.dirname(path), target))
        return resolve_in_root(root, target, depth + 1)
    return host


def find_in_path(root: str, name: str) -> str | None:
    if "/" in name:
        resolved = resolve_in_root(root, name)
        return resolved if resolved and os.path.isfile(resolved) else None
    for directory in DEFAULT_PATH_DIRS:
        resolved = resolve_in_root(root, f"{directory}/{name}")
        if resolved and os.path.isfile(resolved):
            return resolved
    return None


def desktop_exec_binary(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("Exec="):
            rest = line[len("Exec="):].strip()
            return rest.split()[0] if rest else None
    return None


def desktop_exec_has(content: str, flag: str) -> bool:
    for line in content.splitlines():
        if line.startswith("Exec="):
            return flag in line
    return False


def list_desktop_files(root: str) -> list[tuple[str, str]]:
    """(path, content) for every .desktop file in APPLICATIONS_DIR."""
    directory = os.path.join(root, APPLICATIONS_DIR.lstrip("/"))
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []

    found = []
    for name in names:
        if not name.endswith(".desktop"):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        found.append((path, content))
    return found


def find_desktop_file_for_binary(root: str, binary_names: set[str]) -> tuple[str, str] | None:
    """The first .desktop file whose Exec resolves to one of `binary_names`,
    matched by basename since Exec is not necessarily an absolute path."""
    for path, content in list_desktop_files(root):
        exec_binary = desktop_exec_binary(content)
        if not exec_binary:
            continue
        resolved = find_in_path(root, exec_binary)
        if resolved and os.path.basename(resolved) in binary_names:
            return path, content
    return None


def patch_desktop_exec(content: str, binary: str, extra_args: str) -> str:
    """Append `extra_args` right after `binary` on its Exec= line.

    Guarded against duplication so re-running a fix after it already
    applied is a no-op rather than appending the same flags again.
    """
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("Exec="):
            continue
        value = line[len("Exec="):]
        if value.split()[0] != binary or extra_args in value:
            continue
        lines[i] = f"Exec={binary} {extra_args}{value[len(binary):]}"
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")
