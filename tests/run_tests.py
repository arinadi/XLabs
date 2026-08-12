#!/usr/bin/env python3
"""Headless tests for the XLabs TUI and helpers.

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

from textual.widgets import Button, DataTable, Input, RichLog, Select

from installer import app as app_module
from installer import audio, backup, doctor, packages, system
from installer.app import (
    ActionScreen,
    AddRepoScreen,
    XLabsApp,
    BackupScreen,
    ConfirmScreen,
    DoctorScreen,
    DupesScreen,
    MainScreen,
    MirrorScreen,
    ReposScreen,
    SettingsScreen,
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
    script = os.path.join(tempfile.gettempdir(), "xlabs-progress-probe.py")
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


def test_pull_image_falls_back_to_docker_hub() -> None:
    """GHCR has no pull-rate limit for a public package, but some ISPs route
    its Fastly-backed CDN badly. Docker Hub is faster there but rate-limits
    anonymous pulls per IP — shared with every other subscriber behind the
    same carrier-grade NAT on mobile data. pull_image() must try GHCR
    first and only fall back to Docker Hub if that genuinely failed."""
    original_stream_cmd = system.stream_cmd
    original_run_cmd = system.run_cmd
    original_is_installed = system.is_installed
    calls: list[str] = []

    def fake_run_cmd(cmd: str, timeout: int = 60):
        calls.append(cmd)
        return 0, ""

    try:
        # Primary works: no fallback attempted at all.
        system.stream_cmd = lambda cmd, log, timeout=1800: calls.append(cmd) or 0
        system.run_cmd = fake_run_cmd
        system.is_installed = lambda: True
        calls.clear()
        lines: list[str] = []
        check(system.pull_image(lines.append), "reported failure when the primary pull worked")
        # Exactly one attempt — the fallback ref is a substring of the
        # primary one ("arinadi/xlabs" inside "ghcr.io/arinadi/..."),
        # so a call count is the only unambiguous way to prove no retry.
        check(len(calls) == 1, f"fell back when the primary pull already worked: {calls}")

        # Primary fails, fallback works: the partial container must be
        # removed before retrying, and the fallback registry gets a turn.
        attempts = {"n": 0}

        def stream_then_succeed(cmd: str, log, timeout=1800):
            calls.append(cmd)
            attempts["n"] += 1
            return 1 if attempts["n"] == 1 else 0

        system.stream_cmd = stream_then_succeed
        calls.clear()
        lines2: list[str] = []
        check(system.pull_image(lines2.append), "did not recover via the fallback registry")
        check(
            any(c.startswith("proot-distro remove") for c in calls),
            f"did not clean up the partial container before retrying: {calls}",
        )
        installs = [c for c in calls if c.startswith("proot-distro install")]
        check(len(installs) == 2, f"expected a second install attempt, got: {installs}")
        check(
            installs[0] != installs[1],
            f"the second attempt used the same command as the first: {installs}",
        )

        # Both fail: must report failure rather than claim success.
        system.stream_cmd = lambda cmd, log, timeout=1800: calls.append(cmd) or 1
        system.is_installed = lambda: False
        calls.clear()
        lines3: list[str] = []
        check(not system.pull_image(lines3.append), "claimed success when both registries failed")
        check(lines3, "the failure was not explained")
    finally:
        system.stream_cmd = original_stream_cmd
        system.run_cmd = original_run_cmd
        system.is_installed = original_is_installed


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


def test_config_roundtrip(tmp_key: str = "XLABS_TEST_KEY") -> None:
    """The .env holds per-device settings, so writing one key must not lose
    the others."""
    from installer import config

    original = config.load()
    try:
        check(config.set_value(tmp_key, "one"), "could not write the config")
        check(config.get(tmp_key) == "one", "value did not round-trip")

        check(config.set_value("XLABS_TEST_OTHER", "two"), "second write failed")
        check(config.get(tmp_key) == "one", "writing one key dropped another")

        # Comments and blank lines must not become keys.
        check("#" not in "".join(config.load()), "a comment was parsed as a key")
    finally:
        config.unset(tmp_key)
        config.unset("XLABS_TEST_OTHER")

    check(config.get(tmp_key) is None, "unset left the key behind")
    for key, value in original.items():
        check(config.get(key) == value, f"the test disturbed {key}")


def test_draw_path_roundtrip() -> None:
    """termux-x11's rendering flags (Settings) are picked from a fixed
    set; an unknown or missing .env value must fall back to normal rather
    than reach start_x11() and break the launch command."""
    from installer import config, start

    original = config.get(start.DRAW_PATH_KEY)
    try:
        check(start.load_draw_path() in start.DRAW_PATHS, "default draw path is not a known one")

        check(start.save_draw_path("force-bgra"), "could not save a known draw path")
        check(start.load_draw_path() == "force-bgra", "did not round-trip")

        check(not start.save_draw_path("not-a-real-path"), "accepted an unknown draw path")
        check(start.load_draw_path() == "force-bgra", "an invalid save changed the saved value")

        config.set_value(start.DRAW_PATH_KEY, "garbage")
        check(
            start.load_draw_path() == start.DEFAULT_DRAW_PATH,
            "a corrupted .env value was not caught by load_draw_path",
        )
    finally:
        if original is None:
            config.unset(start.DRAW_PATH_KEY)
        else:
            config.set_value(start.DRAW_PATH_KEY, original)


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


def test_mirror_reapplied_after_container_install() -> None:
    """A Reset reinstalls the image, which reverts sources.list to
    DEFAULT_MIRROR — a previously measured mirror choice (Settings) must
    come back on its own rather than silently reverting every time."""
    from installer import config

    fake_root = tempfile.mkdtemp()
    target = os.path.join(fake_root, "etc", "apt", "sources.list.d", "debian.sources")
    os.makedirs(os.path.dirname(target))

    original_container_path = packages.container_path
    original_update_lists = packages.update_lists
    original_mirror_key = config.get(packages.MIRROR_KEY)
    packages.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    packages.update_lists = lambda log: True

    def write(content: str) -> None:
        with open(target, "w", newline="\n") as f:
            f.write(content)

    try:
        config.unset(packages.MIRROR_KEY)
        write(_sample_sources())
        check(
            packages.reapply_saved_mirror(lambda m: None),
            "a no-op reapply (nothing saved yet) reported failure",
        )
        check(
            packages.current_mirror() == "http://deb.debian.org/debian/",
            "a no-op reapply touched the sources file",
        )

        fast_mirror = "http://kartolo.sby.datautama.net.id/debian/"
        check(
            packages.set_mirror(fast_mirror, lambda m: None),
            "set_mirror reported failure on a working update",
        )
        check(
            config.get(packages.MIRROR_KEY) == fast_mirror,
            "set_mirror did not remember the choice for later",
        )

        # A fresh container image always starts back at the default mirror.
        write(_sample_sources())
        check(
            packages.current_mirror() == "http://deb.debian.org/debian/",
            "test setup did not reproduce a freshly reinstalled container",
        )
        check(
            packages.reapply_saved_mirror(lambda m: None),
            "reapply reported failure",
        )
        check(
            packages.current_mirror() == fast_mirror,
            "the saved mirror was not reapplied after reinstall",
        )
    finally:
        packages.container_path = original_container_path
        packages.update_lists = original_update_lists
        if original_mirror_key is None:
            config.unset(packages.MIRROR_KEY)
        else:
            config.set_value(packages.MIRROR_KEY, original_mirror_key)


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


def test_backup_list_and_human_size() -> None:
    """list_backups() must only see its own archives, newest first, and
    survive a BACKUP_DIR that does not exist yet."""
    check(backup.list_backups() == [], "a missing BACKUP_DIR must read as no backups, not an error")

    for byte_count, expected in ((0, "0B"), (999, "999B"), (2048, "2.0KB"), (5 * 1024**3, "5.0GB")):
        check(
            backup.human_size(byte_count) == expected,
            f"human_size({byte_count}) = {backup.human_size(byte_count)!r}, expected {expected!r}",
        )

    fake_dir = tempfile.mkdtemp()
    original_dir = backup.BACKUP_DIR
    backup.BACKUP_DIR = fake_dir
    try:
        for name, age in (("home-20240101-000000.tar.gz", 200), ("home-20240102-000000.tar.gz", 100)):
            path = os.path.join(fake_dir, name)
            with open(path, "wb") as f:
                f.write(b"0" * 1024)
            then = time.time() - age
            os.utime(path, (then, then))
        # Not a backup this tool made — must not show up or be touchable.
        with open(os.path.join(fake_dir, "notes.txt"), "w") as f:
            f.write("hello")

        found = backup.list_backups()
        check(len(found) == 2, f"expected 2 backups, got {len(found)}: {found}")
        check(found[0].name == "home-20240102-000000.tar.gz", "not sorted newest first")
        check(all(b.name.endswith(".tar.gz") for b in found), "a non-archive file was listed")
        check(found[0].size_bytes == 1024, "size was not read from the file")
    finally:
        backup.BACKUP_DIR = original_dir


async def test_backup_screen() -> None:
    """Backup/Restore/Delete all need a highlighted row; without one they
    must warn rather than crash or silently do nothing. Restore is the one
    that can undo real work if it lands on the wrong archive, so — like
    Repos and Mirror — the pick is named on the note line as soon as a row
    is highlighted, not only inside the confirm dialog that follows it."""
    fake_dir = tempfile.mkdtemp()
    original_dir = backup.BACKUP_DIR
    backup.BACKUP_DIR = fake_dir
    try:
        app = XLabsApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#backup")
            await pilot.pause()
            check(isinstance(app.screen, BackupScreen), f"got {app.screen!r}")

            # No backups yet: Restore/Delete must warn, not crash or guess.
            for button in ("#restore", "#delete"):
                await pilot.click(button)
                await pilot.pause()
                check(
                    isinstance(app.screen, BackupScreen),
                    f"{button} with nothing to select left the screen",
                )

            path = os.path.join(fake_dir, "home-20240101-000000.tar.gz")
            with open(path, "wb") as f:
                f.write(b"0" * 2048)
            app.screen._fill()
            await pilot.pause()

            # DataTable highlights row 0 by default the moment rows exist.
            check(
                app.screen.status_text.startswith("Selected:"),
                f"the default row highlight did not update the note: {app.screen.status_text!r}",
            )
            check(
                "home-20240101-000000.tar.gz" in app.screen.status_text,
                f"the note did not name the highlighted archive: {app.screen.status_text!r}",
            )

            await pilot.click("#restore")
            await pilot.pause()
            check(isinstance(app.screen, ConfirmScreen), "Restore with a row selected did not confirm")
            await pilot.click("#cancel")
            await pilot.pause()

            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, MainScreen), "back from Backup did not return")
    finally:
        backup.BACKUP_DIR = original_dir


async def test_settings_screen() -> None:
    """Settings edits must be saved through each owning module (audio.py,
    bench.py, start.py) rather than duplicating their logic, and opening
    the screen must not itself count as an edit — Select.value is set
    programmatically on every visit to show the current pick, which would
    otherwise read back as a user changing it."""
    from installer import audio, bench, config, start

    keys = (audio.METHOD_KEY, bench.PROFILE_KEY, bench.SCORE_KEY, start.DRAW_PATH_KEY)
    original = {k: config.get(k) for k in keys}

    app = XLabsApp()
    try:
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#settings")
            await pilot.pause()
            check(isinstance(app.screen, SettingsScreen), f"got {app.screen!r}")

            check(
                config.get(audio.METHOD_KEY) == original[audio.METHOD_KEY],
                "opening Settings wrote the audio method",
            )
            check(
                config.get(start.DRAW_PATH_KEY) == original[start.DRAW_PATH_KEY],
                "opening Settings wrote the draw path",
            )
            check(app.screen.status_text == "", "a status message appeared before any edit")

            select = app.screen.query_one("#settings-x11", Select)
            check(
                select.value == start.load_draw_path(),
                "the X11 select did not show the currently saved value",
            )

            select.value = "force-bgra"
            await pilot.pause()
            check(start.load_draw_path() == "force-bgra", "changing the select did not save")
            check(
                "saved" in app.screen.status_text.lower(),
                f"no confirmation shown after an edit: {app.screen.status_text!r}",
            )

            payload = app.screen.copy_payload()
            check("force-bgra" in payload, f"copy payload missed the change: {payload!r}")
            # Raises OutOfBounds if the button is not on screen — every
            # other CopyableScreen has one; this one shipped without it.
            await pilot.click("#copy")
            await pilot.pause()

            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, MainScreen), "back from Settings did not return")
    finally:
        for key, value in original.items():
            if value is None:
                config.unset(key)
            else:
                config.set_value(key, value)


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


def test_bench_set_profile_manually_clears_score() -> None:
    """A Settings override (set_profile_manually) has no measured score —
    leaving a stale one from an earlier benchmark would misreport the
    override as something Bench actually measured."""
    from installer import bench, config

    original_profile = config.get(bench.PROFILE_KEY)
    original_score = config.get(bench.SCORE_KEY)
    try:
        check(bench.save_profile(bench.PRESETS[0], 42), "could not save a measured profile")
        check(config.get(bench.SCORE_KEY) == "42", "score did not round-trip")

        check(bench.set_profile_manually(bench.PRESETS[1]), "manual override reported failure")
        check(bench.load_profile() is bench.PRESETS[1], "manual override did not stick")
        check(config.get(bench.SCORE_KEY) is None, "a stale score survived a manual override")
    finally:
        for key, value in (
            (bench.PROFILE_KEY, original_profile),
            (bench.SCORE_KEY, original_score),
        ):
            if value is None:
                config.unset(key)
            else:
                config.set_value(key, value)


def test_audio_test_tone_is_valid() -> None:
    """The tone is generated rather than shipped, so it must be a real WAV."""
    import wave

    path = os.path.join(tempfile.gettempdir(), "xlabs-tone-probe.wav")
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
    app = XLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")

        await pilot.click("#tools")
        await pilot.pause()
        check(isinstance(app.screen, ToolsScreen), f"got {app.screen!r}")
        await pilot.click("#back")
        await pilot.pause()

        await pilot.click("#doctor")
        await pilot.pause()
        check(isinstance(app.screen, DoctorScreen), f"got {app.screen!r}")
        rows = await _wait_for_rows(pilot, app, "#doctor-table")
        # >=12 rather than the old >=8: Internet and Python are folded in
        # from the removed Status screen as real Issues now.
        check(rows >= 12, f"expected >=12 doctor rows, got {rows}")
        check(
            {"Internet", "Python"} <= {i.name for i in app.screen._issues},
            "Internet/Python were not folded in from the old Status screen",
        )
        check(
            "Desktop:" in app.screen._info and "Cache:" in app.screen._info,
            f"Status's running/cache/version facts were not folded in: {app.screen._info!r}",
        )

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
    app = XLabsApp()
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

    app = XLabsApp()
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
    """The diagnostic screen must be able to hand its text back out."""
    app = XLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()

        await pilot.click("#doctor")
        await pilot.pause()
        await _wait_for_rows(pilot, app, "#doctor-table")

        screen = app.screen
        screen.query_one("#copy", Button)
        payload = screen.copy_payload()
        check(payload.strip(), "Doctor produced an empty copy payload")
        check("XLabs" in payload, f"Doctor payload has no header: {payload[:40]!r}")

        await pilot.click("#copy")
        await pilot.pause()
        check(
            os.path.exists(_expected_export_path()),
            "copy did not mirror the output to a file",
        )

        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), "Doctor did not return to the menu")


async def test_narrow_terminal_layout() -> None:
    """Every control must stay on screen at phone widths.

    Regression: a fifth button on Doctor pushed Back off screen, and it only
    surfaced as an OutOfBounds click at 80 columns — a real phone is narrower.
    """
    for width in (40, 45, 60):
        app = XLabsApp()
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

            await pilot.click("#doctor")
            await pilot.pause()
            await _wait_for_rows(pilot, app, "#doctor-table")
            # Raises OutOfBounds if the control is not on screen.
            await pilot.click("#copy")
            await pilot.pause()

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
                f"Doctor did not return at {width} columns",
            )

            # Raises OutOfBounds if Settings or its Back button is not
            # reachable — three Select widgets stacked in a VerticalScroll,
            # the same shape that pushed Back off screen on Repos once.
            await pilot.click("#settings")
            await pilot.pause()
            check(isinstance(app.screen, SettingsScreen), f"got {app.screen!r}")
            await pilot.click("#back")
            await pilot.pause()
            check(
                isinstance(app.screen, MainScreen),
                f"Settings did not return at {width} columns",
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

    app = XLabsApp()
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
        "Signed-By: /etc/apt/keyrings/xlabs-syncthing.asc" in stanza,
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
        app = XLabsApp()
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
    app = XLabsApp()
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
    app = XLabsApp()
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
    """Copying must not conjure ~/XLabs on a machine without a checkout."""
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
        test_pull_image_falls_back_to_docker_hub,
        test_preflight_shape,
        test_doctor_scan_shape,
        test_firefox_prefs_are_defaults_not_locks,
        test_config_roundtrip,
        test_draw_path_roundtrip,
        test_set_mirror_protects_security,
        test_mirror_reapplied_after_container_install,
        test_doctor_reports_security_archive,
        test_electron_sandbox_detection_and_fix,
        test_resolv_conf_check_and_fix,
        test_timezone_check_and_fix,
        test_storage_check_and_cleanup_guard,
        test_backup_list_and_human_size,
        test_backup_screen,
        test_settings_screen,
        test_bench_presets_are_coherent,
        test_bench_set_profile_manually_clears_score,
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
