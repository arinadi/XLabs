"""installer/doctor.py: diagnosis and repair.

    python tests/test_doctor.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from installer import doctor


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


def test_doctor_reports_security_archive() -> None:
    """The shadowing bug mypy caught: a loop variable named `packages` hid
    the module import for the rest of diagnose(), so this check silently
    referenced a list instead of installer.packages and crashed at runtime
    the moment a container existed."""
    issues = doctor.diagnose()
    names = {i.name for i in issues}
    if doctor.is_installed():
        check("Security archive" in names, "the check did not run with a container present")
    else:
        check(
            "Security archive" not in names,
            "the check ran with no container to check",
        )


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


def test_doctor_reports_audio() -> None:
    names = {i.name for i in doctor.diagnose()}
    for expected in ("Audio server", "Audio reachable", "Audio output"):
        check(expected in names, f"{expected} missing from the diagnosis")


TESTS = [
    test_doctor_scan_shape,
    test_doctor_reports_security_archive,
    test_resolv_conf_check_and_fix,
    test_timezone_check_and_fix,
    test_storage_check_and_cleanup_guard,
    test_doctor_reports_audio,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
