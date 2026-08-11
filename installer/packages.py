"""Search and install Debian packages inside the container.

Search terms and package names reach a shell, so they are validated against a
strict pattern and rejected rather than escaped. The scripts themselves are
written into the container and run by path, which is how everything else here
avoids nested quoting.
"""

from __future__ import annotations

import os
import re
from typing import Callable, NamedTuple

from .system import (
    container_command,
    container_path,
    is_installed,
    run_cmd,
    stream_cmd,
    write_container_script,
)

Log = Callable[[str], None]

# Debian package names are lowercase alphanumerics plus . + - and must start
# with an alphanumeric. Search terms are held to the same shape: it costs a
# little expressiveness and removes shell metacharacters entirely.
SAFE_TERM = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,63}$")

SEARCH_LIMIT = 60

SEARCH_SCRIPT = f"""#!/bin/bash
# $1 = search term. Output: <mark>|<name>|<description>
apt-cache search --names-only "$1" 2>/dev/null | head -{SEARCH_LIMIT} \\
    > /tmp/arinanolabs-search.out
dpkg-query -W -f='${{Package}}\\n' 2>/dev/null | sort -u \\
    > /tmp/arinanolabs-installed.out

while IFS= read -r line; do
    name="${{line%% - *}}"
    desc="${{line#* - }}"
    if grep -qxF "$name" /tmp/arinanolabs-installed.out; then
        printf 'I|%s|%s\\n' "$name" "$desc"
    else
        printf ' |%s|%s\\n' "$name" "$desc"
    fi
done < /tmp/arinanolabs-search.out
"""

UPDATE_SCRIPT = """#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
apt-get update
"""

INSTALL_SCRIPT = """#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y "$@"
"""


class Package(NamedTuple):
    name: str
    description: str
    installed: bool


def valid_term(term: str) -> bool:
    return bool(SAFE_TERM.match(term.strip().lower()))


def _noop(_message: str) -> None:
    pass


def lists_present() -> bool:
    """Whether the container has any apt package lists.

    The image ships without them: every Dockerfile layer ends with
    `rm -rf /var/lib/apt/lists/*` to keep the download small. apt-cache
    searches those lists, so on a fresh container every search matches
    nothing — which reads as "the package does not exist" rather than "there
    is nothing to search".
    """
    try:
        entries = os.listdir(container_path("/var/lib/apt/lists"))
    except OSError:
        return False
    return any(name not in {"lock", "partial", "auxfiles"} for name in entries)


def update_lists(log: Log) -> bool:
    """Fetch the package lists. Slow, so it streams."""
    if not write_container_script("arinanolabs-update.sh", UPDATE_SCRIPT):
        log("Could not write the update script.")
        return False
    log("Fetching package lists (the image ships without them)...")
    rc = stream_cmd(container_command("arinanolabs-update.sh"), log, timeout=900)
    log(f"apt-get update exit {rc}")
    return rc == 0


def search(term: str, log: Log = _noop) -> tuple[list[Package], str | None]:
    """Search the container's package lists.

    Returns (results, error). An error is a sentence for the user, not a
    traceback — the raw command and its output go to `log`, so a failure can
    be read rather than guessed at.
    """
    term = term.strip().lower()
    if not term:
        return [], "Type something to search for."
    if not valid_term(term):
        return [], "Use letters, digits, dot, plus or dash only."
    if not is_installed():
        return [], "No container yet — install it from the menu first."

    if not lists_present() and not update_lists(log):
        return [], "Could not fetch the package lists — see the output below."

    if not write_container_script("arinanolabs-search.sh", SEARCH_SCRIPT):
        return [], "Could not write the search script."

    command = f"{container_command('arinanolabs-search.sh')} {term}"
    log(f"$ {command}")
    rc, out = run_cmd(command, timeout=120)
    log(f"exit {rc}, {len(out.splitlines())} line(s)")
    for line in out.strip().splitlines()[:6]:
        log(f"  {line}")

    if rc != 0:
        return [], "The container could not be queried — see the output below."

    results = []
    for line in out.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        mark, name, description = parts
        if not name:
            continue
        results.append(Package(name, description.strip(), mark.strip() == "I"))

    if not results:
        return [], f"Nothing matched '{term}'."
    return results, None


def install(names: list[str], log: Log) -> bool:
    """Install packages into the container."""
    rejected = [n for n in names if not valid_term(n)]
    if rejected:
        log(f"[red]Refusing these names: {', '.join(rejected)}[/red]")
        return False
    if not names:
        log("Nothing selected.")
        return True

    if not write_container_script("arinanolabs-install.sh", INSTALL_SCRIPT):
        log("[red]Could not write the install script.[/red]")
        return False

    log(f"Installing into the container: {', '.join(names)}")
    log("")
    rc = stream_cmd(
        f"{container_command('arinanolabs-install.sh')} {' '.join(names)}",
        log,
        timeout=1800,
    )
    return rc == 0
