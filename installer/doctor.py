"""Diagnose the Termux environment and repair what can be repaired.

Every issue carries its own fix, so the UI does not need to know how any of
them work — it renders the list and calls `fix(log)` on the ones that have
one. An issue with `fix=None` needs the user; say so in `detail`.

Electron sandbox patching, Termux/container duplicate detection, and
Firefox/Chromium tuning each grew into enough of their own thing to live in
electron.py, duplicates.py, and browser.py — this module wires their results
into the issue list rather than implementing them inline.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Callable, NamedTuple

from . import audio, browser, electron, fonts, packages
from . import start as desktop
from .const import (
    LAUNCHER_SRC,
    PREFIX_BIN,
    REPO_DIR,
    TMPDIR,
)
from .preflight import X11_APK_URL, check_internet, check_python, check_storage, check_x11_app
from .system import (
    container_command,
    container_path,
    ensure_home_bin_on_path,
    is_installed,
    link_launcher,
    pull_image,
    run_cmd,
    stream_cmd,
    write_container_script,
)

Log = Callable[[str], None]

# preflight.check_storage() defaults to 4 GB — enough to install the image
# from nothing. Once a container exists, the floor that actually matters is
# how little is left before apt or a download starts failing outright.
STORAGE_MIN_GB = 1.5


class Issue(NamedTuple):
    name: str
    ok: bool
    detail: str
    fix: Callable[[Log], bool] | None = None
    # The check could not be performed — not the same as "the thing is absent".
    unknown: bool = False


# ── Fixes ──────────────────────────────────────────────────


def _fix_launcher(log: Log) -> bool:
    linked, where = link_launcher()
    if not linked:
        log(f"  {where}")
        return False
    log(f"  linked {where} -> {LAUNCHER_SRC}")
    if not where.startswith(PREFIX_BIN):
        for rc in ensure_home_bin_on_path():
            log(f"  added ~/bin to PATH in {rc}")
        log("  open a new session for PATH to take effect")
    return True


def _fix_pip(log: Log) -> bool:
    req = os.path.join(REPO_DIR, "requirements.txt")
    target = f"-r {req}" if os.path.exists(req) else "textual"
    # sys.executable, not "python3": on a device with more than one Python the
    # repair would otherwise install into an interpreter the TUI never uses
    # and then report success.
    for flag in ("", " --break-system-packages", " --user"):
        if stream_cmd(
            f'"{sys.executable}" -m pip install {target}{flag}', log, timeout=600
        ) == 0:
            return True
    return False


def _pkg_fix(label: str, packages: list[str], with_x11_repo: bool = False):
    def fix(log: Log) -> bool:
        if with_x11_repo:
            log(f"  enabling x11-repo first ({label} lives there)")
            if stream_cmd("pkg install -y x11-repo", log, timeout=600) != 0:
                return False
            stream_cmd("pkg update -y", log, timeout=600)
        return stream_cmd(f"pkg install -y {' '.join(packages)}", log, timeout=900) == 0

    return fix


def _fix_container(log: Log) -> bool:
    log("  pulling the image — this takes a few minutes")
    ok = pull_image(log)
    if ok:
        packages.reapply_saved_mirror(log)
    return ok


def _fix_stale_sockets(log: Log) -> bool:
    for path in (f"{TMPDIR}/.X11-unix", f"{TMPDIR}/.X*-lock"):
        run_cmd(f"rm -rf {path} 2>/dev/null")
        log(f"  removed {path}")
    return True


CLEAN_SCRIPT = """#!/bin/bash
apt-get clean
apt-get autoremove -y
"""


def _fix_storage(log: Log) -> bool:
    """apt cache and orphaned packages — the only space a repair can free
    without deleting something the user put there themselves."""
    if not is_installed():
        log("  no container to clean up")
        return False
    if not write_container_script("xlabs-clean.sh", CLEAN_SCRIPT):
        log("  could not write the cleanup script")
        return False
    rc = stream_cmd(container_command("xlabs-clean.sh"), log, timeout=300)
    return rc == 0


# ── Diagnosis ──────────────────────────────────────────────


def _stale_sockets_present() -> bool:
    """X11 leftovers with nothing running to own them.

    A stale .X0-lock is the usual reason a restart fails with the server
    claiming display :0 is already in use.
    """
    if desktop.is_running():
        return False
    rc, _ = run_cmd("pgrep -f termux-x11")
    if rc == 0:
        return False
    if os.path.exists(f"{TMPDIR}/.X11-unix/X0"):
        return True
    return any(
        name.startswith(".X") and name.endswith("-lock")
        for name in (os.listdir(TMPDIR) if os.path.isdir(TMPDIR) else [])
    )


def diagnose() -> list[Issue]:
    issues: list[Issue] = []

    # Repo — nothing else can be fixed without it.
    repo_ok = os.path.isdir(os.path.join(REPO_DIR, ".git"))
    issues.append(
        Issue(
            "Repository",
            repo_ok,
            REPO_DIR if repo_ok else f"{REPO_DIR} is not a git checkout — re-run install.sh",
        )
    )

    # Internet and Python — folded in from the old Status screen. Neither
    # is fixable from here, so fix stays None; they still belong in one
    # place with everything else rather than a separate read-only screen
    # that duplicated half of this one.
    internet = check_internet()
    issues.append(Issue("Internet", internet.ok, internet.message))

    python = check_python()
    issues.append(Issue("Python", python.ok, python.message))

    # Storage. Only worth an auto-fix once there is a container to clean —
    # apt's cache is the only space a repair can free without deleting
    # something the user put there themselves.
    storage = check_storage(STORAGE_MIN_GB)
    issues.append(
        Issue(
            "Storage",
            storage.ok,
            storage.message,
            _fix_storage if not storage.ok and is_installed() else None,
        )
    )

    # Launcher on PATH.
    found = shutil.which("xlabs")
    if found:
        target = os.path.realpath(found)
        correct = target == os.path.realpath(LAUNCHER_SRC)
        issues.append(
            Issue(
                "Launcher",
                correct,
                found if correct else f"{found} points at {target}",
                None if correct else _fix_launcher,
            )
        )
    else:
        issues.append(
            Issue("Launcher", False, "xlabs is not on PATH", _fix_launcher)
        )

    # Python libraries.
    try:
        import textual  # noqa: F401

        issues.append(Issue("Textual", True, "Installed"))
    except ImportError:
        issues.append(Issue("Textual", False, "Not installed", _fix_pip))

    # Termux packages. Loop variable deliberately not named `packages` — that
    # shadowed the installer.packages module import for the rest of this
    # function, and mypy caught the fallout: CANONICAL_SECURITY_URI and
    # repair_security below resolved against a list, not the module.
    for name, binary, pkg_names, x11 in (
        ("proot-distro", "proot-distro", ["proot-distro"], False),
        ("PulseAudio", "pulseaudio", ["pulseaudio"], False),
        ("Termux:X11", "termux-x11", ["termux-x11-nightly", "xorg-xrandr"], True),
        # Without this the desktop runs on llvmpipe. It lives in x11-repo and
        # works on most devices, unlike the zink server.
        ("GPU renderer", "virgl_test_server_android", ["virglrenderer-android"], True),
    ):
        present = shutil.which(binary) is not None
        issues.append(
            Issue(
                name,
                present,
                "Installed" if present else "Missing",
                None if present else _pkg_fix(name, pkg_names, x11),
            )
        )

    # The Android app cannot be installed from here.
    app = check_x11_app()
    if app.ok:
        detail = app.message
    elif app.unknown:
        detail = f"{app.message} — if the desktop shows, it is installed"
    else:
        detail = f"Missing — sideload from {X11_APK_URL}"
    issues.append(Issue("X11 app", app.ok, detail, unknown=app.unknown))

    # Container.
    container = is_installed()
    issues.append(
        Issue(
            "Container",
            container,
            "Installed" if container else "Not installed",
            None if container else _fix_container,
        )
    )

    # Audio. Which method works is a device question, so report the one in
    # use and whether it is actually reachable.
    method = audio.load_method()
    server = audio.server_running()
    issues.append(
        Issue(
            "Audio server",
            server,
            f"{method.name} — {method.server}" if server else "PulseAudio is not running",
            None if server else audio.ensure_server,
        )
    )

    live = server and audio.reachable(method)
    issues.append(
        Issue(
            "Audio reachable",
            live,
            "Answering" if live else f"No answer on {method.server} — run Audio to test methods",
            None if live else audio.ensure_server,
        )
    )

    if is_installed():
        client = audio.client_conf_present()
        issues.append(
            Issue(
                "Audio client",
                client,
                audio.CLIENT_CONF if client else "No client.conf in the container",
                None if client else (lambda log: audio.write_client_conf(method, log)),
            )
        )

    sink_names = audio.sinks()
    issues.append(
        Issue(
            "Audio output",
            bool(sink_names),
            ", ".join(sink_names) if sink_names
            else "No sink — Android has nothing to play through",
        )
    )

    # Security archive. A mirror switch made before Suites-based detection
    # existed could have left this pointing anywhere, and there is no reason
    # to wait for another switch to notice.
    if is_installed():
        current_security = packages.security_uri()
        security_ok = current_security == packages.CANONICAL_SECURITY_URI
        issues.append(
            Issue(
                "Security archive",
                security_ok,
                current_security or "No security stanza found",
                None if security_ok else packages.repair_security,
            )
        )

    # DNS. A container can reach an IP but not a hostname when resolv.conf
    # is empty or a dead symlink — apt then fails with "Temporary failure in
    # name resolution" while `ping 1.1.1.1` works fine, which reads as a
    # dead mirror rather than what it actually is.
    if is_installed():
        dns_ok = _resolv_conf_ok()
        issues.append(
            Issue(
                "DNS",
                dns_ok,
                "resolv.conf has a nameserver" if dns_ok
                else "No usable nameserver in resolv.conf",
                None if dns_ok else _fix_resolv_conf,
            )
        )

    # Timezone. The image ships UTC and nothing ever points it at the
    # device's own zone, so file timestamps and the clock in a terminal
    # inside the container silently disagree with Android's.
    if is_installed():
        android_tz = _android_timezone()
        if android_tz:
            container_tz = _container_timezone()
            tz_ok = container_tz == android_tz
            issues.append(
                Issue(
                    "Timezone",
                    tz_ok,
                    container_tz or "Not set",
                    None if tz_ok else _fix_timezone,
                )
            )

    # Electron apps (VS Code and anything else installed later) — only
    # worth mentioning once at least one is actually present.
    if is_installed():
        electron_found, electron_missing = electron.electron_status()
        if electron_found:
            electron_ok = electron_missing == 0
            issues.append(
                Issue(
                    "Electron apps",
                    electron_ok,
                    "sandbox disabled" if electron_ok
                    else f"{electron_missing} of {electron_found} still need --no-sandbox",
                    None if electron_ok else electron.fix_electron_sandbox,
                )
            )

    # Firefox and Chromium tuning — video codec defaults and the safe
    # performance tier from browser.py, each independently checkable/
    # fixable. The reduced-security tier is deliberately not offered here:
    # it needs its own explicit confirmation, not a blanket Doctor Fix
    # silently taking it — see Doctor Tools -> Browser.
    if browser.firefox_present():
        video_ok = browser.firefox_video_prefs_ok()
        issues.append(
            Issue(
                "Firefox video",
                video_ok,
                "H.264 preferred" if video_ok
                else "VP9/AV1 enabled — software decoded, stutters on YouTube",
                None if video_ok else browser.apply_firefox_video_prefs,
            )
        )
        safe_ok = browser.firefox_safe_tuning_ok()
        issues.append(
            Issue(
                "Firefox tuning",
                safe_ok,
                "Applied" if safe_ok
                else "Default process count and disk cache — see Doctor Tools -> Browser",
                None if safe_ok else browser.apply_firefox_safe_tuning,
            )
        )

    if browser.chromium_present():
        chromium_ok = bool(browser.chromium_tuning_ok())
        issues.append(
            Issue(
                "Chromium tuning",
                chromium_ok,
                "Applied" if chromium_ok
                else "Default flags — see Doctor Tools -> Browser",
                None if chromium_ok else browser.apply_chromium_tuning,
            )
        )

    # Fonts — color emoji plus a ligature-friendly terminal font. Not baked
    # into the image outright; see fonts.py for why these two specifically
    # (validated against issue #6's audit rather than taken on its word).
    if is_installed():
        fonts_ok = fonts.fonts_ready()
        issues.append(
            Issue(
                "Fonts",
                fonts_ok,
                "Noto Color Emoji + Fira Code installed and active" if fonts_ok
                else "Missing or not activated — see Doctor Fix",
                None if fonts_ok else fonts.install_and_activate,
            )
        )

    # Leftovers from a bad shutdown.
    stale = _stale_sockets_present()
    issues.append(
        Issue(
            "X11 sockets",
            not stale,
            "Stale lock or socket with nothing running" if stale else "Clean",
            _fix_stale_sockets if stale else None,
        )
    )

    return issues


# ── DNS ────────────────────────────────────────────────────

# A container can reach an IP but not a hostname when resolv.conf is empty
# or a dead symlink (e.g. to systemd-resolved, which does not run under
# proot) — apt then fails with "Temporary failure in name resolution" while
# a plain ping to an IP works, which reads as a dead mirror rather than
# what it actually is.
RESOLV_CONF = "/etc/resolv.conf"
RESOLV_CONF_CONTENT = "nameserver 1.1.1.1\nnameserver 8.8.8.8\n"


def _resolv_conf_ok() -> bool:
    try:
        with open(container_path(RESOLV_CONF), encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return False
    return any(
        line.strip().startswith("nameserver ") and len(line.strip().split()) >= 2
        for line in content.splitlines()
    )


def _fix_resolv_conf(log: Log) -> bool:
    target = container_path(RESOLV_CONF)
    # A dead symlink still "exists" for os.path.exists() to disagree with —
    # remove whatever is there before writing a real file.
    if os.path.islink(target) or os.path.exists(target):
        try:
            os.remove(target)
        except OSError as e:
            log(f"  could not remove the old {RESOLV_CONF}: {e}")
            return False
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(RESOLV_CONF_CONTENT)
    except OSError as e:
        log(f"  could not write {RESOLV_CONF}: {e}")
        return False
    log(f"  wrote {RESOLV_CONF} (1.1.1.1, 8.8.8.8)")
    return True


# ── Timezone ───────────────────────────────────────────────

# The image ships UTC and nothing ever points it at the device's own zone,
# so file timestamps and the clock in a terminal inside the container
# silently disagree with Android's.
TIMEZONE_FILE = "/etc/timezone"
LOCALTIME_FILE = "/etc/localtime"


def _android_timezone() -> str | None:
    rc, out = run_cmd("getprop persist.sys.timezone", timeout=10)
    tz = out.strip()
    return tz if rc == 0 and tz else None


def _container_timezone() -> str | None:
    try:
        with open(container_path(TIMEZONE_FILE), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _fix_timezone(log: Log) -> bool:
    android_tz = _android_timezone()
    if not android_tz:
        log("  could not read the device timezone (getprop persist.sys.timezone)")
        return False

    if not os.path.isfile(container_path(f"/usr/share/zoneinfo/{android_tz}")):
        log(f"  {android_tz} has no zoneinfo file in the container")
        return False

    localtime = container_path(LOCALTIME_FILE)
    try:
        if os.path.islink(localtime) or os.path.exists(localtime):
            os.remove(localtime)
        os.symlink(f"/usr/share/zoneinfo/{android_tz}", localtime)
    except OSError as e:
        log(f"  could not link {LOCALTIME_FILE}: {e}")
        return False

    try:
        with open(container_path(TIMEZONE_FILE), "w", encoding="utf-8", newline="\n") as f:
            f.write(android_tz + "\n")
    except OSError as e:
        log(f"  could not write {TIMEZONE_FILE}: {e}")
        return False

    log(f"  container timezone set to {android_tz}")
    return True


def fixable(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if not i.ok and i.fix is not None]


def run_fixes(issues: list[Issue], log: Log) -> tuple[int, int]:
    """Apply every available fix. Returns (repaired, attempted)."""
    targets = fixable(issues)
    if not targets:
        log("Nothing to fix.")
        return 0, 0

    repaired = 0
    for issue in targets:
        log(f"[bold]{issue.name}[/bold] — {issue.detail}")
        try:
            assert issue.fix is not None
            if issue.fix(log):
                log("  [green]repaired[/green]")
                repaired += 1
            else:
                log("  [red]could not repair[/red]")
        except Exception as e:
            log(f"  [red]error: {e}[/red]")
        log("")

    return repaired, len(targets)
