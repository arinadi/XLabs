#!/usr/bin/env python3
"""Headless tests for the arinanoLabs TUI and helpers.

Plain script rather than pytest so CI needs no test dependency beyond what
the app already requires. Run from the repo root:

    python tests/run_tests.py

Each test that guards a previously shipped bug says which one, so a future
change that reintroduces it fails with an explanation rather than a number.

Nothing here presses Doctor's Fix button: those repairs run real pip and pkg
installs against the machine running the tests.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.widgets import Button, DataTable, RichLog  # noqa: E402

from installer import app as app_module  # noqa: E402
from installer import doctor  # noqa: E402
from installer.app import (  # noqa: E402
    ActionScreen,
    ArinanoLabsApp,
    ConfirmScreen,
    DoctorScreen,
    MainScreen,
    StatusScreen,
    ToolsScreen,
)
from installer.preflight import run_all_checks  # noqa: E402
from installer.system import stream_cmd  # noqa: E402

_failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ── Tests ──────────────────────────────────────────────────


def test_stream_cmd_timeout_kills_silent_process() -> None:
    """Regression: the deadline used to be checked only when a line arrived.

    A command producing no output therefore ran to completion no matter the
    timeout, so every long operation in the app had no working limit.
    """
    silent = f'"{sys.executable}" -c "import time; time.sleep(20)"'
    start = time.monotonic()
    rc = stream_cmd(silent, lambda _m: None, timeout=2)
    elapsed = time.monotonic() - start

    check(elapsed < 10, f"timeout did not fire: took {elapsed:.1f}s")
    check(rc == 1, f"expected rc=1 on timeout, got {rc}")


def test_stream_cmd_returns_output_and_code() -> None:
    lines: list[str] = []
    script = '"%s" -c "print(\'hello\'); raise SystemExit(3)"' % sys.executable
    rc = stream_cmd(script, lines.append, timeout=30)

    check(rc == 3, f"expected rc=3, got {rc}")
    check("hello" in lines, f"output not captured: {lines}")


def test_preflight_shape() -> None:
    checks = run_all_checks()
    names = {c.name for c in checks}

    check(len(checks) >= 6, f"expected at least 6 checks, got {len(checks)}")
    check("X11 app" in names, "X11 app check missing")
    for c in checks:
        check(isinstance(c.unknown, bool), f"{c.name} has no unknown flag")
        # A check may not claim both that it passed and that it could not run.
        check(not (c.ok and c.unknown), f"{c.name} is both ok and unknown")


def test_doctor_scan_shape() -> None:
    issues = doctor.diagnose()
    names = {i.name for i in issues}

    check(len(issues) >= 8, f"expected at least 8 issues, got {len(issues)}")
    for expected in ("Repository", "Launcher", "Container", "X11 sockets"):
        check(expected in names, f"{expected} missing from diagnosis")

    for issue in issues:
        check(not (issue.ok and issue.fix), f"{issue.name} is ok but offers a fix")
        # An unknown result is not actionable, so it must not advertise a fix.
        check(not (issue.unknown and issue.fix), f"{issue.name} is unknown but offers a fix")

    check(
        all(not i.ok for i in doctor.fixable(issues)),
        "fixable() returned an issue that already passes",
    )


async def test_tui_navigation() -> None:
    app = ArinanoLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")

        await pilot.click("#tools")
        await pilot.pause()
        check(isinstance(app.screen, ToolsScreen), f"got {app.screen!r}")
        await pilot.click("#back")
        await pilot.pause()

        await pilot.click("#status")
        await pilot.pause()
        check(isinstance(app.screen, StatusScreen), f"got {app.screen!r}")
        rows = await _wait_for_rows(pilot, app, "#status-table")
        check(rows >= 7, f"expected >=7 status rows, got {rows}")
        await pilot.click("#back")
        await pilot.pause()

        await pilot.click("#doctor")
        await pilot.pause()
        check(isinstance(app.screen, DoctorScreen), f"got {app.screen!r}")
        rows = await _wait_for_rows(pilot, app, "#doctor-table")
        check(rows >= 8, f"expected >=8 doctor rows, got {rows}")

        fixable = [i for i in app.screen._issues if not i.ok and i.fix is not None]
        disabled = app.screen.query_one("#fix", Button).disabled
        check(
            disabled == (not fixable),
            f"Fix button disabled={disabled} but {len(fixable)} issues are fixable",
        )
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


async def test_destructive_actions_are_gated() -> None:
    app = ArinanoLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()

        for button in ("#reset", "#cache"):
            await pilot.click(button)
            await pilot.pause()
            check(isinstance(app.screen, ConfirmScreen), f"{button} skipped confirmation")
            await pilot.click("#cancel")
            await pilot.pause()
            check(isinstance(app.screen, MainScreen), f"cancel on {button} did not return")


async def test_escape_cannot_leave_running_action() -> None:
    """Regression: escape used to walk out of a screen whose Back was disabled.

    Leaving mid image pull abandoned a half-installed container with nothing
    on screen to say so.
    """
    release = threading.Event()

    def blocking(log) -> None:
        log("working")
        release.wait(timeout=15)
        log("done")

    # Drive the real UI path. Pushing a screen from outside the app's own
    # handlers never mounts it, so the runner is swapped instead — that also
    # keeps the test from touching the machine's image cache.
    original = app_module.run_clean_cache
    app_module.run_clean_cache = blocking

    app = ArinanoLabsApp()
    try:
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#cache")
            await pilot.pause()
            await pilot.click("#confirm")

            # pilot.pause() waits on pending messages and times out while a
            # thread worker is blocked, so use plain sleeps until released.
            await asyncio.sleep(0.5)

            screen = app.screen
            check(isinstance(screen, ActionScreen), f"got {screen!r}")
            check(
                screen.query_one("#back", Button).disabled,
                "Back should be disabled while working",
            )

            await pilot.press("escape")
            await asyncio.sleep(0.3)
            check(
                isinstance(app.screen, ActionScreen),
                "escape left a running action screen",
            )

            release.set()
            for _ in range(60):
                await asyncio.sleep(0.1)
                if not app.screen.query_one("#back", Button).disabled:
                    break
            await pilot.pause()

            check(
                not app.screen.query_one("#back", Button).disabled,
                "Back never re-enabled after the worker finished",
            )
            check(app.screen.query_one("#log", RichLog).lines, "no output was written")

            await pilot.press("escape")
            await pilot.pause()
            check(isinstance(app.screen, MainScreen), "escape did not leave a finished screen")
    finally:
        app_module.run_clean_cache = original
        release.set()


async def test_copy_buttons_export_output() -> None:
    """Every diagnostic screen must be able to hand its text back out."""
    app = ArinanoLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()

        for entry, table in (("#status", "#status-table"), ("#doctor", "#doctor-table")):
            await pilot.click(entry)
            await pilot.pause()
            await _wait_for_rows(pilot, app, table)

            screen = app.screen
            screen.query_one("#copy", Button)
            payload = screen.copy_payload()
            check(payload.strip(), f"{entry} produced an empty copy payload")
            check("arinanoLabs" in payload, f"{entry} payload has no header: {payload[:40]!r}")

            await pilot.click("#copy")
            await pilot.pause()
            check(
                os.path.exists(_expected_export_path()),
                "copy did not mirror the output to a file",
            )

            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, MainScreen), f"{entry} did not return to the menu")


async def test_narrow_terminal_layout() -> None:
    """Every control must stay reachable on a phone-width terminal.

    Regression: adding a fifth button to Doctor pushed Back off screen, which
    only showed up as an OutOfBounds click at 80 columns — a real phone is
    narrower still.
    """
    app = ArinanoLabsApp()
    async with app.run_test(size=(45, 30)) as pilot:
        await pilot.pause()

        for entry, table in (("#status", "#status-table"), ("#doctor", "#doctor-table")):
            await pilot.click(entry)
            await pilot.pause()
            await _wait_for_rows(pilot, app, table)
            # Raises OutOfBounds if the control is not on screen.
            await pilot.click("#copy")
            await pilot.pause()
            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, MainScreen), f"{entry} did not return at 45 cols")

        await pilot.click("#tools")
        await pilot.pause()
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), "tools did not return at 45 cols")


def _expected_export_path() -> str:
    directory = (
        app_module.REPO_DIR
        if os.path.isdir(app_module.REPO_DIR)
        else tempfile.gettempdir()
    )
    return os.path.join(directory, app_module.EXPORT_NAME)


def test_export_never_creates_a_repo_directory() -> None:
    """Copying must not conjure ~/arinanoLabs on a machine without a checkout."""
    if os.path.isdir(app_module.REPO_DIR):
        return  # nothing to prove on a real checkout
    app_module._write_export("probe")
    check(
        not os.path.isdir(app_module.REPO_DIR),
        f"copying created {app_module.REPO_DIR}",
    )


# ── Runner ─────────────────────────────────────────────────


async def _wait_for_rows(pilot, app, selector: str, attempts: int = 80) -> int:
    for _ in range(attempts):
        await asyncio.sleep(0.1)
        await pilot.pause()
        rows = app.screen.query_one(selector, DataTable).row_count
        if rows:
            return rows
    return app.screen.query_one(selector, DataTable).row_count


def main() -> int:
    tests = [
        test_stream_cmd_timeout_kills_silent_process,
        test_stream_cmd_returns_output_and_code,
        test_preflight_shape,
        test_doctor_scan_shape,
        test_tui_navigation,
        test_destructive_actions_are_gated,
        test_escape_cannot_leave_running_action,
        test_copy_buttons_export_output,
        test_narrow_terminal_layout,
        test_export_never_creates_a_repo_directory,
    ]

    for test in tests:
        name = test.__name__
        try:
            if asyncio.iscoroutinefunction(test):
                asyncio.run(test())
            else:
                test()
        except Exception:  # noqa: BLE001 - every failure is reported, none stop the run
            _failures.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
        else:
            print(f"ok    {name}")

    print()
    if _failures:
        print(f"{len(_failures)} of {len(tests)} failed: {', '.join(_failures)}")
        return 1
    print(f"all {len(tests)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
