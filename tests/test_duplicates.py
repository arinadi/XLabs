"""installer/duplicates.py: Termux packages the container already provides.

    python tests/test_duplicates.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from installer import duplicates


def test_termux_duplicates_are_safe() -> None:
    """Never offer to remove anything outside the candidate list."""
    dupes = duplicates.termux_duplicates()
    check(isinstance(dupes, list), f"expected a list, got {type(dupes)}")
    for dupe in dupes:
        check(
            dupe.package in duplicates.TERMUX_DUPLICATES,
            f"{dupe.package} is not a removal candidate",
        )

    # Everything the project itself runs on must be unreachable by this path.
    for essential in (
        "python", "python-pip", "git", "proot-distro", "termux-x11-nightly",
        "pulseaudio", "termux-tools", "bash", "coreutils", "apt", "dpkg",
        "mesa-zink", "virglrenderer-android", "angle-android",
    ):
        check(
            essential not in duplicates.TERMUX_DUPLICATES,
            f"{essential} must never be a removal candidate",
        )

    lines: list[str] = []
    check(
        not duplicates.remove_termux_packages(["coreutils"], lines.append),
        "removing a non-candidate package was not refused",
    )
    check(
        any("Refusing" in line for line in lines),
        f"refusal was not explained: {lines}",
    )


TESTS = [
    test_termux_duplicates_are_safe,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
