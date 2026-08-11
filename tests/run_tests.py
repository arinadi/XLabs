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

from textual.widgets import Button, DataTable, Input, RichLog, Static  # noqa: E402

from installer import app as app_module  # noqa: E402
from installer import audio  # noqa: E402
from installer import doctor  # noqa: E402
from installer import packages  # noqa: E402
from installer.app import (  # noqa: E402
    ActionScreen,
    ArinanoLabsApp,
    ConfirmScreen,
    DoctorScreen,
    DupesScreen,
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


def test_stream_cmd_shows_carriage_return_progress() -> None:
    """Regression: downloaders redraw one line with CR and emit no newline.

    A line-based reader showed nothing for the whole transfer, so pulling the
    image looked frozen.
    """
    # chr(13)/chr(10) rather than escapes: this source is written to a file
    # and read back, and backslashes do not survive that round trip cleanly.
    probe = "\n".join([
        "import sys, time",
        "for i in range(0, 101, 25):",
        "    sys.stdout.write(chr(13) + 'Downloading %d%%' % i)",
        "    sys.stdout.flush()",
        "    time.sleep(0.05)",
        "sys.stdout.write(chr(10) + 'Done' + chr(10))",
    ])
    script = os.path.join(tempfile.gettempdir(), "arinanolabs-progress-probe.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(probe)

    command = '"%s" "%s"' % (sys.executable, script)

    class Logger(list):
        def __call__(self, message=""):
            self.append(("log", message))

        def progress(self, message):
            self.append(("progress", message))

    logger = Logger()
    rc = stream_cmd(command, logger, timeout=30)
    check(rc == 0, f"expected rc=0, got {rc}: {list(logger)}")

    progress = [m for kind, m in logger if kind == "progress"]
    check(len(progress) >= 3, f"progress was not reported live: {list(logger)}")
    check(
        any("Done" in m for kind, m in logger if kind == "log"),
        f"the final line never arrived: {list(logger)}",
    )

    # Without .progress() the redraws are throttled into the log rather than
    # flooding it.
    plain: list[str] = []
    rc = stream_cmd(command, plain.append, timeout=30)
    check(rc == 0, f"expected rc=0, got {rc}: {plain}")
    check(plain, "the throttled path produced nothing at all")
    check(len(plain) < 6, f"the throttled path flooded the log: {plain}")

    os.remove(script)


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


def test_firefox_prefs_are_defaults_not_locks() -> None:
    """The video tuning must set defaults the user can still override."""
    body = doctor.FIREFOX_PREFS
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        check(
            stripped.startswith("pref(") and stripped.endswith(");"),
            f"unexpected line in the prefs file: {line!r}",
        )
        # lockPref would stop about:config from changing it.
        check("lockPref" not in stripped, f"prefs must not lock: {line!r}")

    for expected in ("media.mediasource.vp9.enabled", "media.av1.enabled"):
        check(expected in body, f"{expected} missing from the prefs")

    # Without a container there is nothing to tune, so the check stays out of
    # the way rather than reporting a problem that cannot exist yet.
    if not doctor.is_installed():
        names = {i.name for i in doctor.diagnose()}
        check("Firefox video" not in names, "reported Firefox with no container")

    # The repair refuses rather than raising when the target is absent.
    lines: list[str] = []
    if not os.path.isdir(doctor._container_path(doctor.FIREFOX_PREFS_DIR)):
        check(
            not doctor._fix_firefox_prefs(lines.append),
            "the repair claimed success with no container",
        )
        check(lines, "the repair explained nothing")


def test_audio_test_tone_is_valid() -> None:
    """The tone is generated rather than shipped, so it must be a real WAV."""
    import wave

    path = os.path.join(tempfile.gettempdir(), "arinanolabs-tone-probe.wav")
    check(audio.write_test_tone(path, seconds=0.2), "the tone was not written")
    with wave.open(path) as handle:
        check(handle.getnchannels() == 1, "expected mono")
        check(handle.getsampwidth() == 2, "expected 16-bit samples")
        check(handle.getnframes() > 0, "the tone has no frames")
    os.remove(path)


def test_doctor_reports_audio() -> None:
    names = {i.name for i in doctor.diagnose()}
    for expected in ("Audio server", "Audio over TCP", "Audio output"):
        check(expected in names, f"{expected} missing from the diagnosis")


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
    """Every control must stay on screen at phone widths.

    Regression: a fifth button on Doctor pushed Back off screen, and it only
    surfaced as an OutOfBounds click at 80 columns — a real phone is narrower.
    """
    for width in (40, 45, 60):
        app = ArinanoLabsApp()
        async with app.run_test(size=(width, 30)) as pilot:
            await pilot.pause()

            screen = app.screen
            for button in screen.query(Button):
                check(
                    screen.region.contains_region(button.region),
                    f"{button.id} is off screen at {width} columns: "
                    f"{button.region} outside {screen.region}",
                )
                check(
                    button.region.width >= len(str(button.label)),
                    f"{button.id} label '{button.label}' is wider than its "
                    f"{button.region.width}-column button at {width} columns",
                )

            for entry, table in (("#status", "#status-table"), ("#doctor", "#doctor-table")):
                await pilot.click(entry)
                await pilot.pause()
                await _wait_for_rows(pilot, app, table)
                # Raises OutOfBounds if the control is not on screen.
                await pilot.click("#copy")
                await pilot.pause()

                if entry == "#doctor":
                    # Reached through Doctor, so it needs checking at width too.
                    await pilot.click("#dupes")
                    await pilot.pause()
                    check(isinstance(app.screen, DupesScreen), f"got {app.screen!r}")
                    await pilot.click("#copy")
                    await pilot.pause()
                    await pilot.click("#back")
                    await pilot.pause()
                    check(isinstance(app.screen, DoctorScreen), "dupes did not return")

                await pilot.click("#back")
                await pilot.pause()
                check(
                    isinstance(app.screen, MainScreen),
                    f"{entry} did not return at {width} columns",
                )


async def test_update_offers_restart() -> None:
    """Update should be able to relaunch onto the code it just pulled.

    The runner is swapped for a controllable one: the real update finishes
    instantly when there is no checkout, which would make the "disabled while
    working" assertion a race.
    """
    release = threading.Event()

    def blocking(log) -> None:
        log("pulling")
        release.wait(timeout=15)

    original = app_module.run_update
    app_module.run_update = blocking

    app = ArinanoLabsApp()
    try:
        async with app.run_test(size=(60, 30)) as pilot:
            await pilot.pause()
            check(app.restart_requested is False, "restart wanted before it was asked for")

            await pilot.click("#update")
            await asyncio.sleep(0.5)

            screen = app.screen
            check(isinstance(screen, ActionScreen), f"got {screen!r}")
            check(
                screen.query_one("#restart", Button).disabled,
                "restart was offered while the update was still running",
            )

            release.set()
            for _ in range(80):
                await asyncio.sleep(0.1)
                if not app.screen.query_one("#back", Button).disabled:
                    break
            await pilot.pause()

            check(
                not app.screen.query_one("#restart", Button).disabled,
                "restart stayed disabled after the update finished",
            )

            await pilot.click("#restart")
            await pilot.pause()
            check(app.restart_requested, "pressing Restart did not request one")
    finally:
        app_module.run_update = original
        release.set()


def test_other_actions_do_not_offer_restart() -> None:
    """Only Update relaunches. Everything else just returns to the menu."""
    plain = ActionScreen("Plain", lambda log: None)
    check(plain._offer_restart is False, "restart is opt-in and was not requested")


def test_package_terms_reject_shell_metacharacters() -> None:
    """Search terms and package names reach a shell, so they are validated."""
    for good in ("neovim", "python3-pip", "libgl1-mesa-dri", "g++", "bat"):
        check(packages.valid_term(good), f"{good!r} should be accepted")

    hostile = [
        "a; rm -rf /", "a && whoami", "a | tee x", "a`id`", "a$(id)",
        "a\nb", "../etc/passwd", "a b", "'", '"', "$PATH", "a>b", "",
        "x" * 80,
    ]
    for term in hostile:
        check(not packages.valid_term(term), f"{term!r} should be rejected")

    lines: list[str] = []
    check(
        not packages.install(["neovim; rm -rf /"], lines.append),
        "install accepted a name with shell syntax",
    )
    check(any("Refusing" in line for line in lines), f"no refusal logged: {lines}")

    results, error = packages.search("a; rm -rf /")
    check(results == [], "a hostile search returned results")
    check(error is not None, "a hostile search reported no error")


async def test_tools_screen_searches() -> None:
    app = ArinanoLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#tools")
        await pilot.pause()
        check(isinstance(app.screen, ToolsScreen), f"got {app.screen!r}")

        check(
            app.screen.query_one("#install", Button).disabled,
            "Install was offered before any search",
        )

        # No container off-device, so this exercises the error path.
        app.screen.query_one("#query", Input).value = "neovim"
        await pilot.press("enter")
        for _ in range(40):
            await asyncio.sleep(0.1)
            await pilot.pause()
            if "Searching" not in app.screen.status_text:
                break
        check(app.screen.status_text, "the search reported nothing at all")
        check(
            "Searching" not in app.screen.status_text,
            f"the search never finished: {app.screen.status_text!r}",
        )
        check(
            app.screen.query_one("#install", Button).disabled,
            "Install was enabled with no results",
        )

        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


def _expected_export_path() -> str:
    directory = (
        app_module.REPO_DIR
        if os.path.isdir(app_module.REPO_DIR)
        else tempfile.gettempdir()
    )
    return os.path.join(directory, app_module.EXPORT_NAME)


def test_termux_duplicates_are_safe() -> None:
    """Never offer to remove anything outside the candidate list."""
    dupes = doctor.termux_duplicates()
    check(isinstance(dupes, list), f"expected a list, got {type(dupes)}")
    for dupe in dupes:
        check(
            dupe.package in doctor.TERMUX_DUPLICATES,
            f"{dupe.package} is not a removal candidate",
        )

    # Everything the project itself runs on must be unreachable by this path.
    for essential in (
        "python", "python-pip", "git", "proot-distro", "termux-x11-nightly",
        "pulseaudio", "termux-tools", "bash", "coreutils", "apt", "dpkg",
        "mesa-zink", "virglrenderer-android", "angle-android",
    ):
        check(
            essential not in doctor.TERMUX_DUPLICATES,
            f"{essential} must never be a removal candidate",
        )

    lines: list[str] = []
    check(
        not doctor.remove_termux_packages(["coreutils"], lines.append),
        "removing a non-candidate package was not refused",
    )
    check(
        any("Refusing" in line for line in lines),
        f"refusal was not explained: {lines}",
    )


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
        test_stream_cmd_shows_carriage_return_progress,
        test_preflight_shape,
        test_doctor_scan_shape,
        test_firefox_prefs_are_defaults_not_locks,
        test_audio_test_tone_is_valid,
        test_doctor_reports_audio,
        test_tui_navigation,
        test_destructive_actions_are_gated,
        test_escape_cannot_leave_running_action,
        test_copy_buttons_export_output,
        test_narrow_terminal_layout,
        test_termux_duplicates_are_safe,
        test_update_offers_restart,
        test_package_terms_reject_shell_metacharacters,
        test_tools_screen_searches,
        test_other_actions_do_not_offer_restart,
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
