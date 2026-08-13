"""installer/electron.py: --no-sandbox patching for Electron apps.

    python tests/test_electron.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from installer import electron


def test_electron_sandbox_detection_and_fix() -> None:
    """VS Code (and anything else Electron) opens nothing under proot: the
    SUID sandbox needs unprivileged user namespaces proot only fakes, so
    Chromium's zygote init fails and the app never appears. It finds every
    installed Electron app by the chrome-sandbox helper next to its binary —
    not by name, so something besides VS Code is caught too — and patches
    its .desktop Exec with --no-sandbox."""
    fake_root = tempfile.mkdtemp()
    apps_dir = os.path.join(fake_root, "usr", "share", "applications")
    code_dir = os.path.join(fake_root, "opt", "code")
    bin_dir = os.path.join(fake_root, "usr", "bin")
    os.makedirs(apps_dir)
    os.makedirs(code_dir)
    os.makedirs(bin_dir)

    open(os.path.join(code_dir, "code"), "w").close()
    open(os.path.join(code_dir, "chrome-sandbox"), "w").close()
    code_desktop = os.path.join(apps_dir, "code.desktop")
    with open(code_desktop, "w", newline="\n") as f:
        f.write(
            "[Desktop Entry]\n"
            "Name=Visual Studio Code\n"
            "Exec=/opt/code/code --unity-launch %F\n"
            "Type=Application\n"
        )

    # A non-Electron app in a different directory, with no sandbox helper
    # anywhere near it, must not be touched.
    open(os.path.join(bin_dir, "htop"), "w").close()
    htop_desktop = os.path.join(apps_dir, "htop.desktop")
    with open(htop_desktop, "w", newline="\n") as f:
        f.write("[Desktop Entry]\nName=htop\nExec=/usr/bin/htop\nType=Application\n")

    original_container_path = electron.container_path
    electron.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    try:
        found, missing = electron.electron_status()
        check(found == 1, f"expected exactly the Electron app to be found, got {found}")
        check(missing == 1, "a freshly-written .desktop must not already look patched")

        lines: list[str] = []
        check(electron.fix_electron_sandbox(lines.append), "the fix reported failure")

        patched = open(code_desktop).read()
        check("--no-sandbox" in patched, "Exec was not patched")
        check("--unity-launch" in patched, "the fix dropped an existing flag")
        check("%F" in patched, "the fix dropped the file-open field code")

        untouched = open(htop_desktop).read()
        check("--no-sandbox" not in untouched, "a non-Electron app was patched")

        found, missing = electron.electron_status()
        check(missing == 0, "the app still reports as unpatched after the fix")

        # Re-running must not add a second --no-sandbox.
        lines2: list[str] = []
        check(electron.fix_electron_sandbox(lines2.append), "the re-run reported failure")
        check(
            open(code_desktop).read().count("--no-sandbox") == 1,
            "re-running the fix duplicated the flag",
        )
    finally:
        electron.container_path = original_container_path


TESTS = [
    test_electron_sandbox_detection_and_fix,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
