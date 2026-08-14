"""installer/fonts.py: Doctor's font install + activate fix.

    python tests/test_fonts.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from installer import fonts


def test_patch_ini_section_creates_missing_section() -> None:
    lines = ["[Other]", "Foo=bar"]
    result = fonts._patch_ini_section(lines, "[Configuration]", {"FontName": "Fira Code 11"})
    check(result[0] == "[Configuration]", "the new section was not placed first")
    check("FontName=Fira Code 11" in result, "the new key is missing")
    check("[Other]" in result and "Foo=bar" in result, "an unrelated section was disturbed")


def test_patch_ini_section_updates_existing_key_in_place() -> None:
    lines = ["[Configuration]", "FontName=Monospace 12", "MiscBell=FALSE", "[Dialog]", "X=1"]
    result = fonts._patch_ini_section(lines, "[Configuration]", {"FontName": "Fira Code 11"})
    check(result == ["[Configuration]", "FontName=Fira Code 11", "MiscBell=FALSE", "[Dialog]", "X=1"],
          f"unexpected patch result: {result!r}")


def test_patch_ini_section_appends_missing_key_within_section() -> None:
    lines = ["[Configuration]", "MiscBell=FALSE", "[Dialog]", "X=1"]
    result = fonts._patch_ini_section(
        lines, "[Configuration]", {"FontName": "Fira Code 11", "FontUseSystem": "FALSE"}
    )
    # Both new keys must land inside [Configuration], before [Dialog] starts.
    dialog_index = result.index("[Dialog]")
    check("FontName=Fira Code 11" in result[:dialog_index], "FontName landed outside its section")
    check("FontUseSystem=FALSE" in result[:dialog_index], "FontUseSystem landed outside its section")
    check(result[dialog_index:] == ["[Dialog]", "X=1"], "an unrelated section was disturbed")


def test_terminal_font_activation_roundtrip() -> None:
    """A fresh container has no terminalrc at all until xfce4-terminal is
    launched once — activation must create one rather than require it to
    pre-exist, and must leave an existing one's other settings alone."""
    fake_root = tempfile.mkdtemp()
    original_container_path = fonts.container_path
    fonts.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    try:
        check(not fonts.terminal_font_active(), "a missing terminalrc must not read as active")

        lines: list[str] = []
        check(fonts._activate_terminal_font(lines.append), "activation reported failure")
        check(fonts.terminal_font_active(), "the font was not recognised as active afterwards")

        # A real, hand-edited terminalrc with unrelated settings must survive.
        target = fonts.container_path(fonts.TERMINAL_RC)
        with open(target, "w", newline="\n") as f:
            f.write("[Configuration]\nFontName=Monospace 12\nMiscAlwaysShowTabs=TRUE\n")
        check(not fonts.terminal_font_active(), "test setup did not reset to inactive")

        check(fonts._activate_terminal_font(lambda m: None), "re-activation reported failure")
        check(fonts.terminal_font_active(), "re-activation did not take")
        content = open(target).read()
        check("MiscAlwaysShowTabs=TRUE" in content, "activation disturbed an unrelated setting")
    finally:
        fonts.container_path = original_container_path


def test_install_and_activate_skips_apt_when_already_installed() -> None:
    """Re-running the Doctor fix after the packages are already there must
    only touch the terminal font, not re-run apt every time."""
    fake_root = tempfile.mkdtemp()
    original_container_path = fonts.container_path
    original_is_installed = fonts.is_installed
    original_installed_packages = fonts._installed_packages
    original_stream_cmd = fonts.stream_cmd

    fonts.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    fonts.is_installed = lambda: True
    fonts._installed_packages = lambda: set(fonts.PACKAGES)
    calls: list[str] = []
    fonts.stream_cmd = lambda cmd, log, timeout=300: calls.append(cmd) or 0

    try:
        lines: list[str] = []
        check(fonts.install_and_activate(lines.append), "install_and_activate reported failure")
        check(not calls, "apt was invoked even though the packages were already installed")
        check(fonts.terminal_font_active(), "the terminal font was not activated")
    finally:
        fonts.container_path = original_container_path
        fonts.is_installed = original_is_installed
        fonts._installed_packages = original_installed_packages
        fonts.stream_cmd = original_stream_cmd


def test_install_and_activate_runs_apt_when_missing() -> None:
    fake_root = tempfile.mkdtemp()
    original_container_path = fonts.container_path
    original_is_installed = fonts.is_installed
    original_installed_packages = fonts._installed_packages
    original_stream_cmd = fonts.stream_cmd

    fonts.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    fonts.is_installed = lambda: True
    fonts._installed_packages = lambda: set()
    calls: list[str] = []
    fonts.stream_cmd = lambda cmd, log, timeout=300: calls.append(cmd) or 0

    try:
        lines: list[str] = []
        check(fonts.install_and_activate(lines.append), "install_and_activate reported failure")
        check(calls, "apt was never invoked for a missing font package")
        check(fonts.terminal_font_active(), "the terminal font was not activated")
    finally:
        fonts.container_path = original_container_path
        fonts.is_installed = original_is_installed
        fonts._installed_packages = original_installed_packages
        fonts.stream_cmd = original_stream_cmd


def test_install_and_activate_refuses_without_container() -> None:
    original_is_installed = fonts.is_installed
    fonts.is_installed = lambda: False
    try:
        lines: list[str] = []
        check(not fonts.install_and_activate(lines.append), "claimed success with no container")
        check(lines, "the refusal was not explained")
    finally:
        fonts.is_installed = original_is_installed


TESTS = [
    test_patch_ini_section_creates_missing_section,
    test_patch_ini_section_updates_existing_key_in_place,
    test_patch_ini_section_appends_missing_key_within_section,
    test_terminal_font_activation_roundtrip,
    test_install_and_activate_skips_apt_when_already_installed,
    test_install_and_activate_runs_apt_when_missing,
    test_install_and_activate_refuses_without_container,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
