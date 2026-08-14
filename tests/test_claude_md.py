"""installer/claude_md.py: ~/.claude/CLAUDE.md inside the container.

    python tests/test_claude_md.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from installer import claude_md


def _isolated(test):
    def wrapper() -> None:
        fake_root = tempfile.mkdtemp()
        original_container_path = claude_md.container_path
        claude_md.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
        try:
            test(fake_root)
        finally:
            claude_md.container_path = original_container_path

    wrapper.__name__ = test.__name__
    return wrapper


@_isolated
def test_read_missing_file_is_empty(fake_root: str) -> None:
    check(claude_md.read() == "", "reading a nonexistent CLAUDE.md returned non-empty text")


@_isolated
def test_write_read_roundtrip(fake_root: str) -> None:
    lines: list[str] = []
    check(claude_md.write("# Notes\n\nBe terse.\n", lines.append), "write reported failure")
    check(claude_md.read() == "# Notes\n\nBe terse.\n", "content did not round-trip")
    check(any("saved" in line for line in lines), f"no confirmation logged: {lines}")

    # Overwriting must replace, not append.
    check(claude_md.write("Replaced.\n", lines.append), "second write reported failure")
    check(claude_md.read() == "Replaced.\n", "second write did not replace the first")


TESTS = [
    test_read_missing_file_is_empty,
    test_write_read_roundtrip,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
