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

from textual.widgets import Button, DataTable, Input, RichLog

from installer import app as app_module
from installer import audio, doctor, packages
from installer.app import (
    ActionScreen,
    AddRepoScreen,
    ArinanoLabsApp,
    ConfirmScreen,
    DoctorScreen,
    DupesScreen,
    MainScreen,
    MirrorScreen,
    ReposScreen,
    StatusScreen,
    SwapScreen,
    ToolsScreen,
)
from installer.preflight import run_all_checks
from installer.system import container_path, stream_cmd

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
    if not os.path.isdir(container_path(doctor.FIREFOX_PREFS_DIR)):
        check(
            not doctor._fix_firefox_prefs(lines.append),
            "the repair claimed success with no container",
        )
        check(lines, "the repair explained nothing")


def test_config_roundtrip(tmp_key: str = "ARINANOLABS_TEST_KEY") -> None:
    """The .env holds per-device settings, so writing one key must not lose
    the others."""
    from installer import config

    original = config.load()
    try:
        check(config.set_value(tmp_key, "one"), "could not write the config")
        check(config.get(tmp_key) == "one", "value did not round-trip")

        check(config.set_value("ARINANOLABS_TEST_OTHER", "two"), "second write failed")
        check(config.get(tmp_key) == "one", "writing one key dropped another")

        # Comments and blank lines must not become keys.
        check("#" not in "".join(config.load()), "a comment was parsed as a key")
    finally:
        config.unset(tmp_key)
        config.unset("ARINANOLABS_TEST_OTHER")

    check(config.get(tmp_key) is None, "unset left the key behind")
    for key, value in original.items():
        check(config.get(key) == value, f"the test disturbed {key}")


def _sample_sources(security_uri: str = "https://security.debian.org/debian-security") -> str:
    return (
        "Types: deb\n"
        "URIs: http://deb.debian.org/debian/\n"
        "Suites: trixie trixie-updates\n"
        "Components: main contrib non-free non-free-firmware\n"
        "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n"
        "\n"
        "Types: deb\n"
        f"URIs: {security_uri}\n"
        "Suites: trixie-security\n"
        "Components: main contrib non-free non-free-firmware\n"
        "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n"
    )


def test_set_mirror_protects_security() -> None:
    """Regression, two rounds.

    Round 1 shipped: switching the mirror repointed security at it too,
    which most mirrors do not carry, and apt exited 100. The fix repointed
    security to the canonical URI whenever it recognised the stanza — by
    guessing from the URI's own content.

    Round 2 was reported from a device: guessing from the URI stopped
    working the moment the URI was already wrong, which is exactly the
    state a container corrupted by round 1 was in. A stanza is identified
    by its Suites field now, which a bad URI cannot obscure, and every
    switch repairs security regardless of what it currently says.
    """
    import tempfile

    from installer import packages

    fake_root = tempfile.mkdtemp()
    target = os.path.join(fake_root, "etc", "apt", "sources.list.d", "debian.sources")
    os.makedirs(os.path.dirname(target))

    original_container_path = packages.container_path
    original_update_lists = packages.update_lists
    packages.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))

    def write(content: str) -> None:
        with open(target, "w", newline="\n") as f:
            f.write(content)

    try:
        # Round 1: a healthy file, switching the mirror must not touch
        # security's URI beyond normalising it to the canonical form.
        write(_sample_sources())
        packages.update_lists = lambda log: True
        check(
            packages.set_mirror("http://kartolo.sby.datautama.net.id/debian/", lambda m: None),
            "set_mirror reported failure on a working update",
        )
        result = open(target).read()
        check(
            "http://kartolo.sby.datautama.net.id/debian/" in result,
            "the main archive was not repointed",
        )
        check(
            packages.CANONICAL_SECURITY_URI in result,
            "security did not end up at the canonical URI",
        )

        # Round 2: the exact shape reported from a device — security already
        # corrupted to an unrelated mirror by an earlier, buggy switch, with
        # nothing about its URI left to suggest it was ever security.
        write(_sample_sources(security_uri="http://werog.interkoneksimedia.co.id/debian/"))
        check(
            packages.security_uri() == "http://werog.interkoneksimedia.co.id/debian/",
            "test setup did not reproduce the corrupted state",
        )
        check(
            packages.set_mirror("http://kartolo.sby.datautama.net.id/debian/", lambda m: None),
            "set_mirror reported failure on a working update",
        )
        check(
            packages.security_uri() == packages.CANONICAL_SECURITY_URI,
            "pre-existing corruption survived the switch",
        )

        # repair_security() must also fix it standalone, since Doctor offers
        # it independently of switching mirrors.
        write(_sample_sources(security_uri="http://werog.interkoneksimedia.co.id/debian/"))
        check(packages.repair_security(lambda m: None), "repair_security reported failure")
        check(
            packages.security_uri() == packages.CANONICAL_SECURITY_URI,
            "repair_security did not fix a corrupted stanza",
        )

        # Failure case: a mirror apt cannot use must roll back rather than
        # leave the container stuck.
        write(_sample_sources())
        packages.update_lists = lambda log: False
        check(
            not packages.set_mirror("http://bad-mirror.invalid/debian/", lambda m: None),
            "set_mirror reported success despite update_lists failing",
        )
        restored = open(target).read()
        check(
            "bad-mirror.invalid" not in restored,
            "the bad mirror was left in place instead of rolling back",
        )
        check(
            "http://deb.debian.org/debian/" in restored,
            "the original mirror was not restored",
        )
    finally:
        packages.container_path = original_container_path
        packages.update_lists = original_update_lists


def test_doctor_reports_security_archive() -> None:
    """The shadowing bug mypy caught: a loop variable named `packages` hid
    the module import for the rest of diagnose(), so this check silently
    referenced a list instead of installer.packages and crashed at runtime
    the moment a container existed."""
    from installer import doctor

    issues = doctor.diagnose()
    names = {i.name for i in issues}
    if doctor.is_installed():
        check("Security archive" in names, "the check did not run with a container present")
    else:
        check(
            "Security archive" not in names,
            "the check ran with no container to check",
        )


def test_electron_sandbox_detection_and_fix() -> None:
    """VS Code (and anything else Electron) opens nothing under proot: the
    SUID sandbox needs unprivileged user namespaces proot only fakes, so
    Chromium's zygote init fails and the app never appears. Doctor finds
    every installed Electron app by the chrome-sandbox helper next to its
    binary — not by name, so something besides VS Code is caught too — and
    patches its .desktop Exec with --no-sandbox."""
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

    original_container_path = doctor.container_path
    doctor.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    try:
        found, missing = doctor._electron_status()
        check(found == 1, f"expected exactly the Electron app to be found, got {found}")
        check(missing == 1, "a freshly-written .desktop must not already look patched")

        lines: list[str] = []
        check(doctor._fix_electron_sandbox(lines.append), "the fix reported failure")

        patched = open(code_desktop).read()
        check("--no-sandbox" in patched, "Exec was not patched")
        check("--unity-launch" in patched, "the fix dropped an existing flag")
        check("%F" in patched, "the fix dropped the file-open field code")

        untouched = open(htop_desktop).read()
        check("--no-sandbox" not in untouched, "a non-Electron app was patched")

        found, missing = doctor._electron_status()
        check(missing == 0, "the app still reports as unpatched after the fix")

        # Re-running must not add a second --no-sandbox.
        lines2: list[str] = []
        check(doctor._fix_electron_sandbox(lines2.append), "the re-run reported failure")
        check(
            open(code_desktop).read().count("--no-sandbox") == 1,
            "re-running the fix duplicated the flag",
        )
    finally:
        doctor.container_path = original_container_path


def test_resolv_conf_check_and_fix() -> None:
    """DNS failure reads as a dead mirror ("Temporary failure in name
    resolution") when the real cause is an empty or dangling resolv.conf
    inside the container — this is the check and repair for that."""
    fake_root = tempfile.mkdtemp()
    etc_dir = os.path.join(fake_root, "etc")
    os.makedirs(etc_dir)
    target = os.path.join(etc_dir, "resolv.conf")

    original_container_path = doctor.container_path
    doctor.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    try:
        check(not doctor._resolv_conf_ok(), "a missing resolv.conf must not read as ok")

        with open(target, "w", newline="\n") as f:
            f.write("# empty, generated at container creation\n")
        check(
            not doctor._resolv_conf_ok(),
            "a resolv.conf with no nameserver line must not read as ok",
        )

        lines: list[str] = []
        check(doctor._fix_resolv_conf(lines.append), "the fix reported failure")
        check(doctor._resolv_conf_ok(), "the fix did not leave a usable resolv.conf")
        check("1.1.1.1" in open(target).read(), "the fix did not write a real nameserver")

        with open(target, "w", newline="\n") as f:
            f.write("nameserver 10.0.0.1\n")
        check(doctor._resolv_conf_ok(), "an existing nameserver was not recognised")
    finally:
        doctor.container_path = original_container_path


def test_timezone_check_and_fix() -> None:
    """The image ships UTC; the repair points /etc/localtime at the
    device's own zone once it can tell what that is, and refuses rather
    than writing a dangling symlink for a zone with no zoneinfo file."""
    fake_root = tempfile.mkdtemp()
    os.makedirs(os.path.join(fake_root, "usr", "share", "zoneinfo", "Asia"))
    open(os.path.join(fake_root, "usr", "share", "zoneinfo", "Asia", "Jakarta"), "w").close()
    os.makedirs(os.path.join(fake_root, "etc"))

    original_container_path = doctor.container_path
    original_run_cmd = doctor.run_cmd
    doctor.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    doctor.run_cmd = lambda cmd, timeout=60: (0, "Asia/Jakarta\n")
    try:
        check(
            doctor._android_timezone() == "Asia/Jakarta",
            "did not read the fake getprop output",
        )
        check(
            doctor._container_timezone() is None,
            "a fresh container must not already report a timezone",
        )

        doctor.run_cmd = lambda cmd, timeout=60: (0, "Not/AZone\n")
        lines: list[str] = []
        check(
            not doctor._fix_timezone(lines.append),
            "claimed success for a zone with no zoneinfo file in the container",
        )
        doctor.run_cmd = lambda cmd, timeout=60: (0, "Asia/Jakarta\n")

        if os.name != "nt":
            # Symlink creation needs a privilege this test sandbox may not
            # have on Windows; the logic above it is what matters there.
            check(doctor._fix_timezone(lambda m: None), "the fix reported failure")
            check(
                doctor._container_timezone() == "Asia/Jakarta",
                "/etc/timezone was not written",
            )
            link_target = os.readlink(os.path.join(fake_root, "etc", "localtime"))
            check(
                link_target == "/usr/share/zoneinfo/Asia/Jakarta",
                f"localtime points at {link_target!r}, not the container-relative path",
            )
    finally:
        doctor.container_path = original_container_path
        doctor.run_cmd = original_run_cmd


def test_storage_check_and_cleanup_guard() -> None:
    """The only automatic storage repair is apt cache cleanup, and it must
    refuse rather than pretend when there is no container to clean."""
    if not doctor.is_installed():
        lines: list[str] = []
        check(not doctor._fix_storage(lines.append), "claimed success with no container")
        check(lines, "the refusal was not explained")

    issues = {i.name: i for i in doctor.diagnose()}
    check("Storage" in issues, "Storage must always be reported")
    storage = issues["Storage"]
    if not storage.ok:
        expected_fix = doctor._fix_storage if doctor.is_installed() else None
        check(storage.fix is expected_fix, "Storage repair offered without a container to clean")


def test_swap_never_auto_fixable() -> None:
    """Enabling swap writes multiple GB and turns on kernel swap for the
    rest of the session — it must never be something Fix All can trigger
    unattended, so a Swap Issue must never carry a `fix`."""
    ram_mb, active = doctor.swap_status()
    check(ram_mb is None or isinstance(ram_mb, int), f"unexpected RAM reading: {ram_mb!r}")
    check(isinstance(active, bool), f"unexpected swap-active reading: {active!r}")

    for issue in doctor.diagnose():
        if issue.name == "Swap":
            check(issue.fix is None, "Swap must never carry an automatic fix")


def test_swap_ensures_tools_before_mkswap() -> None:
    """Regression, reported from a device: mkswap/swapon come from
    util-linux, which is not part of Termux's default bootstrap, so a
    fresh install genuinely lacks them — create_swap() used to call
    mkswap directly and fail with "not found" instead of installing it
    first."""
    original_which = doctor.shutil.which
    original_stream_cmd = doctor.stream_cmd
    calls: list[str] = []
    state = {"installed": False}

    def fake_which(name: str):
        if name not in ("mkswap", "swapon"):
            return original_which(name)
        return f"/usr/bin/{name}" if state["installed"] else None

    def fake_stream_cmd(cmd: str, log, timeout: int = 60) -> int:
        calls.append(cmd)
        return 0

    try:
        # Already present: no install attempted.
        state["installed"] = True
        doctor.shutil.which = fake_which
        doctor.stream_cmd = fake_stream_cmd
        check(doctor._ensure_swap_tools(lambda m: None), "reported missing when present")
        check(not calls, "installed util-linux when the tools were already there")

        # Missing, then appear once "installed" — the install must run and
        # the tools must be re-checked afterward rather than assumed.
        state["installed"] = False

        def install_then_appear(cmd: str, log, timeout: int = 60) -> int:
            calls.append(cmd)
            state["installed"] = True
            return 0

        doctor.stream_cmd = install_then_appear
        lines: list[str] = []
        check(doctor._ensure_swap_tools(lines.append), "did not recover after installing")
        check(any("util-linux" in c for c in calls), "did not install util-linux")

        # Missing, and the install itself fails: must not claim success.
        state["installed"] = False
        calls.clear()
        doctor.stream_cmd = fake_stream_cmd  # returns 0 but never flips "installed"

        def failing_stream_cmd(cmd: str, log, timeout: int = 60) -> int:
            calls.append(cmd)
            return 1

        doctor.stream_cmd = failing_stream_cmd
        lines2: list[str] = []
        check(
            not doctor._ensure_swap_tools(lines2.append),
            "claimed success when installing util-linux failed",
        )
        check(lines2, "the failure was not explained")
    finally:
        doctor.shutil.which = original_which
        doctor.stream_cmd = original_stream_cmd


def test_bench_presets_are_coherent() -> None:
    """Every preset must be runnable and its result storable."""
    from installer import bench

    names = [p.name for p in bench.PRESETS]
    check(len(names) == len(set(names)), f"duplicate preset names: {names}")
    check("software" in names, "the software baseline is missing")

    for preset in bench.PRESETS:
        check(bench.preset_by_name(preset.name) is preset, f"{preset.name} not findable")
        exports = bench.client_exports(preset)
        check(exports, f"{preset.name} exports nothing")
        for line in exports.splitlines():
            check(line.startswith("export "), f"{preset.name}: bad export line {line!r}")

    check(
        bench.preset_by_name("nonexistent") is None,
        "an unknown preset name resolved to something",
    )


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
    for expected in ("Audio server", "Audio reachable", "Audio output"):
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

                    # Raises OutOfBounds if Swap is not on screen — this is
                    # the fourth button on that row, added after the fifth-
                    # button regression above, so it needs the same guard.
                    await pilot.click("#swap")
                    await pilot.pause()
                    check(isinstance(app.screen, SwapScreen), f"got {app.screen!r}")
                    await pilot.click("#back")
                    await pilot.pause()
                    check(isinstance(app.screen, DoctorScreen), "swap did not return")

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


def test_search_notices_missing_package_lists() -> None:
    """Regression: the image ships with no apt lists.

    Every Dockerfile layer ends with rm -rf /var/lib/apt/lists/*, so on a
    fresh container apt-cache matches nothing and every search looked like
    "no such package" rather than "nothing to search".
    """
    check(
        isinstance(packages.lists_present(), bool),
        "lists_present must answer with a bool",
    )

    body = packages.SEARCH_SCRIPT
    check("apt-cache search" in body, "the search no longer uses apt-cache")
    check("apt-get update" in packages.UPDATE_SCRIPT, "the update script does not update")

    # Both paths that install must refresh first, or they fail on a fresh
    # container the same way search did.
    check("apt-get update" in packages.INSTALL_SCRIPT, "install does not refresh lists")


def test_validate_custom_repo() -> None:
    """The Add Repo form is a shell-adjacent surface: values land in a
    written apt config and one field's URL is later handed to curl."""
    from installer import packages

    check(
        packages.validate_custom_repo("", "", "", "", "") != [],
        "empty fields must be rejected",
    )
    check(
        packages.validate_custom_repo(
            "syncthing",
            "https://apt.syncthing.net/",
            "syncthing",
            "release",
            "https://syncthing.net/release-key.gpg",
        )
        == [],
        "a well-formed custom repo was rejected",
    )

    # A name colliding with a built-in repo, or one already added, must be
    # refused rather than silently overwriting it.
    for builtin in packages.REPOS:
        check(
            packages.validate_custom_repo(
                builtin.name, "https://x.invalid/", "a", "main", "https://x.invalid/key"
            )
            != [],
            f"the built-in name '{builtin.name}' was accepted for a custom repo",
        )

    # A repo with no key cannot be verified, so it must not be
    # constructible — this is not optional the way it is for backports.
    check(
        packages.validate_custom_repo("nokey", "https://x.invalid/", "a", "main", "") != [],
        "a repo with no signing key was accepted",
    )

    # A newline in any field could smuggle a second apt directive into the
    # stanza (e.g. an extra Signed-By: pointing somewhere else).
    for hostile in (
        "https://x.invalid/\nSigned-By: /etc/shadow",
        "https://x.invalid/ extra",
    ):
        check(
            packages.validate_custom_repo("evil", hostile, "a", "main", "https://x.invalid/key")
            != [],
            f"a hostile URI was accepted: {hostile!r}",
        )

    stanza = packages.build_custom_repo(
        "syncthing",
        "https://apt.syncthing.net/",
        "syncthing",
        "release",
        "https://syncthing.net/release-key.gpg",
    ).stanza
    check("URIs: https://apt.syncthing.net/" in stanza, "URI missing from the built stanza")
    check(
        "Signed-By: /etc/apt/keyrings/arinanolabs-syncthing.asc" in stanza,
        "the stanza does not point at the fetched key",
    )


async def test_add_repo_screen() -> None:
    """The custom-repo form: validation blocks bad input, a good one reaches
    confirmation, and every control stays reachable at phone widths.

    Two clicks on the same button in quick succession is a known pacing
    issue in Textual's test pilot rather than anything about this screen —
    calling the handler directly showed the logic was correct before the
    delay was added, so this is not papering over a real bug.
    """
    for width, height in ((80, 40), (45, 30), (40, 24)):
        app = ArinanoLabsApp()
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            await pilot.click("#tools")
            await pilot.pause()
            await pilot.click("#repos")
            await pilot.pause()
            check(isinstance(app.screen, ReposScreen), f"got {app.screen!r}")
            for button in app.screen.query(Button):
                check(
                    app.screen.region.contains_region(button.region),
                    f"{button.id} off screen at {width}x{height} on ReposScreen",
                )

            await pilot.click("#add")
            await pilot.pause()
            check(isinstance(app.screen, AddRepoScreen), f"got {app.screen!r}")
            for button in app.screen.query(Button):
                check(
                    app.screen.region.contains_region(button.region),
                    f"{button.id} off screen at {width}x{height} on AddRepoScreen",
                )

            await pilot.click("#submit")
            await asyncio.sleep(0.15)
            await pilot.pause()
            check(isinstance(app.screen, AddRepoScreen), "empty submit left the form")
            check("Name:" in app.screen.status_text, f"no validation message: {app.screen.status_text!r}")

            app.screen.query_one("#repo-name", Input).value = "syncthing"
            app.screen.query_one("#repo-uri", Input).value = "https://apt.syncthing.net/"
            app.screen.query_one("#repo-suites", Input).value = "syncthing"
            app.screen.query_one("#repo-key", Input).value = "https://syncthing.net/release-key.gpg"
            await asyncio.sleep(0.15)
            await pilot.pause()

            await pilot.click("#submit")
            await asyncio.sleep(0.15)
            await pilot.pause()
            check(
                isinstance(app.screen, ConfirmScreen),
                f"valid submit did not reach confirmation at {width}x{height}: {app.screen!r}",
            )

            await pilot.click("#cancel")
            await pilot.pause()
            check(isinstance(app.screen, AddRepoScreen), "cancel discarded the form")

            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, ReposScreen), "back from the form did not return")
            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, ToolsScreen), "back from Repos did not return")


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


async def test_row_selection_shows_before_confirm() -> None:
    """A DataTable row is a thin touch target — one line tall, no gutter
    between rows — so a mistap is easy on a phone screen. Repos and Mirror
    both have real data without a container, so highlighting a row there
    must update the status line before any button is pressed, not only
    inside the confirm dialog that follows it."""
    app = ArinanoLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#tools")
        await pilot.pause()

        await pilot.click("#repos")
        await pilot.pause()
        check(isinstance(app.screen, ReposScreen), f"got {app.screen!r}")
        # DataTable highlights row 0 by default the moment rows exist, so
        # the note already names a pick before any tap of its own.
        check(
            app.screen.status_text.startswith("Selected:"),
            f"the default row highlight did not update the note: {app.screen.status_text!r}",
        )
        table = app.screen.query_one("#repos-table", DataTable)
        if table.row_count > 1:
            table.move_cursor(row=1)
            await pilot.pause()
            check(
                app.screen.status_text.startswith("Selected:"),
                f"highlighting a different repo row lost the note: {app.screen.status_text!r}",
            )
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, ToolsScreen), "back from Repos did not return")

        await pilot.click("#mirror")
        await pilot.pause()
        check(isinstance(app.screen, MirrorScreen), f"got {app.screen!r}")
        # DataTable highlights row 0 by default the moment rows exist, so
        # the status line already names a pick before any tap of its own.
        check(
            app.screen.status_text.startswith("Selected:"),
            f"the default row highlight did not update the status: {app.screen.status_text!r}",
        )
        # The regular refresh must still restore it afterward — this is a
        # shared line, not a dedicated one, so nothing may be lost for good.
        app.screen._refresh_current()
        check(
            not app.screen.status_text.startswith("Selected:"),
            "the highlight text survived a refresh instead of being replaced",
        )


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
        test_config_roundtrip,
        test_set_mirror_protects_security,
        test_doctor_reports_security_archive,
        test_electron_sandbox_detection_and_fix,
        test_resolv_conf_check_and_fix,
        test_timezone_check_and_fix,
        test_storage_check_and_cleanup_guard,
        test_swap_never_auto_fixable,
        test_swap_ensures_tools_before_mkswap,
        test_bench_presets_are_coherent,
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
        test_search_notices_missing_package_lists,
        test_validate_custom_repo,
        test_add_repo_screen,
        test_tools_screen_searches,
        test_row_selection_shows_before_confirm,
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
        except Exception:
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
