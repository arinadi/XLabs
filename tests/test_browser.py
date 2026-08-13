"""installer/browser.py: Firefox/Chromium tuning for proot's ptrace overhead.

    python tests/test_browser.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run


def _no_lock_prefs(body: str) -> list[str]:
    """Every non-comment line must be a pref()/user_pref() call, never a
    lockPref() — locking would stop about:config from overriding it."""
    problems = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if not (
            (stripped.startswith("pref(") or stripped.startswith("user_pref("))
            and stripped.endswith(");")
        ):
            problems.append(f"unexpected line: {line!r}")
        if "lockPref" in stripped:
            problems.append(f"prefs must not lock: {line!r}")
    return problems


def test_firefox_video_prefs_are_defaults_not_locks() -> None:
    from installer import browser, doctor

    problems = _no_lock_prefs(browser.FIREFOX_VIDEO_PREFS)
    check(not problems, f"{problems}")

    for expected in ("media.mediasource.vp9.enabled", "media.av1.enabled"):
        check(expected in browser.FIREFOX_VIDEO_PREFS, f"{expected} missing from the prefs")

    # Without a container there is nothing to tune, so the check stays out of
    # the way rather than reporting a problem that cannot exist yet.
    if not doctor.is_installed():
        names = {i.name for i in doctor.diagnose()}
        check("Firefox video" not in names, "reported Firefox with no container")

    # The repair refuses rather than raising when the target is absent.
    lines: list[str] = []
    if not os.path.isdir(browser.container_path(browser.FIREFOX_PREFS_DIR)):
        check(
            not browser.apply_firefox_video_prefs(lines.append),
            "the repair claimed success with no container",
        )
        check(lines, "the repair explained nothing")


def test_firefox_safe_tuning_is_gpu_conditional_and_unlocked() -> None:
    """The safe tier must never contain fission.autostart or Safe Browsing
    changes — those are the reduced-security tier's job, applied only with
    explicit confirmation — and its webrender line must follow whichever
    GPU preset bench.py actually measured, not assume acceleration works."""
    from installer import bench, browser, config

    original_profile = config.get(bench.PROFILE_KEY)
    original_score = config.get(bench.SCORE_KEY)
    try:
        bench.save_profile(bench.preset_by_name("virgl"), 500)
        accelerated_body = browser.FIREFOX_SAFE_PREFS_TEMPLATE.format(
            webrender_line='user_pref("gfx.webrender.all", true);'
            if browser._gpu_accelerated()
            else 'user_pref("gfx.webrender.software", true);'
        )
        check(
            "gfx.webrender.all" in accelerated_body,
            "an accelerated GPU preset did not enable hardware webrender",
        )

        bench.save_profile(bench.preset_by_name("software"), 50)
        software_body = browser.FIREFOX_SAFE_PREFS_TEMPLATE.format(
            webrender_line='user_pref("gfx.webrender.all", true);'
            if browser._gpu_accelerated()
            else 'user_pref("gfx.webrender.software", true);'
        )
        check(
            "gfx.webrender.software" in software_body,
            "a software GPU preset did not fall back to software webrender",
        )

        for body in (accelerated_body, software_body):
            problems = _no_lock_prefs(body)
            check(not problems, f"{problems}")
            check("fission.autostart" not in body, "safe tier leaked a security trade-off")
            check("safebrowsing" not in body, "safe tier leaked a security trade-off")
    finally:
        for key, value in ((bench.PROFILE_KEY, original_profile), (bench.SCORE_KEY, original_score)):
            if value is None:
                config.unset(key)
            else:
                config.set_value(key, value)


def test_firefox_reduced_security_prefs_are_explicit() -> None:
    """The reduced-security tier must actually contain the trade-offs it
    claims to make — a Doctor-style silent Fix must never reach this file,
    only the explicit confirm-gated path in BrowserScreen."""
    from installer import browser

    problems = _no_lock_prefs(browser.FIREFOX_REDUCED_SECURITY_PREFS)
    check(not problems, f"{problems}")
    for expected in (
        'user_pref("fission.autostart", false);',
        "browser.safebrowsing.malware.enabled",
        "browser.safebrowsing.phishing.enabled",
    ):
        check(expected in browser.FIREFOX_REDUCED_SECURITY_PREFS, f"{expected} missing")


def test_chromium_tuning_detects_and_patches() -> None:
    from installer import browser

    fake_root = tempfile.mkdtemp()
    apps_dir = os.path.join(fake_root, "usr", "share", "applications")
    bin_dir = os.path.join(fake_root, "usr", "bin")
    os.makedirs(apps_dir)
    os.makedirs(bin_dir)
    open(os.path.join(bin_dir, "chromium"), "w").close()

    desktop_path = os.path.join(apps_dir, "chromium.desktop")
    with open(desktop_path, "w", newline="\n") as f:
        f.write(
            "[Desktop Entry]\nName=Chromium\nExec=chromium %U\nType=Application\n"
        )

    original_container_path = browser.container_path
    browser.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    try:
        check(
            browser.chromium_tuning_ok() is False,
            "a freshly-written .desktop must not already look tuned",
        )

        lines: list[str] = []
        check(browser.apply_chromium_tuning(lines.append), "the fix reported failure")

        patched = open(desktop_path).read()
        check("--no-sandbox" in patched, "Chromium must get --no-sandbox like any Electron app")
        check(browser.CHROMIUM_TUNING_MARKER in patched, "the marker flag was not applied")
        check("%U" in patched, "the fix dropped the URL-open field code")

        check(browser.chromium_tuning_ok() is True, "still reports untuned after the fix")

        # Re-running must not duplicate any flag.
        lines2: list[str] = []
        check(browser.apply_chromium_tuning(lines2.append), "the re-run reported failure")
        check(
            open(desktop_path).read().count("--no-sandbox") == 1,
            "re-running the fix duplicated --no-sandbox",
        )
    finally:
        browser.container_path = original_container_path


def test_chromium_tuning_ok_is_none_without_chromium() -> None:
    from installer import browser

    fake_root = tempfile.mkdtemp()
    os.makedirs(os.path.join(fake_root, "usr", "share", "applications"))

    original_container_path = browser.container_path
    browser.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
    try:
        check(
            browser.chromium_tuning_ok() is None,
            "no Chromium .desktop entry must report None, not False",
        )
    finally:
        browser.container_path = original_container_path


TESTS = [
    test_firefox_video_prefs_are_defaults_not_locks,
    test_firefox_safe_tuning_is_gpu_conditional_and_unlocked,
    test_firefox_reduced_security_prefs_are_explicit,
    test_chromium_tuning_detects_and_patches,
    test_chromium_tuning_ok_is_none_without_chromium,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
