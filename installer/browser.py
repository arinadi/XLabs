"""Firefox and Chromium tuning for proot's ptrace overhead.

Every open/stat/read/write a browser makes is intercepted in userspace, so
process count and disk-write frequency dominate perceived lag far more than
raw JS/render speed — see the project's browser optimization research for
the reasoning behind each preference below. Two tiers:

- "safe" tuning has no downside beyond what it changes on purpose (fewer
  processes, less disk I/O, no telemetry) and is safe for Doctor's own Fix
  to apply automatically, the same as the existing video-codec defaults.
- "reduced security" trades away Firefox's Fission site isolation and Safe
  Browsing warnings for a further cut in process count and background
  traffic. The research this implements recommends against it, so it is
  never wired into Doctor's Fix — applying it needs its own explicit
  confirmation (Doctor Tools -> Browser).

Chromium's own --no-sandbox is not duplicated from scratch here: electron.py
already catches Chromium (it has the same chrome-sandbox helper next to its
binary as every Electron app), so by the time apply_chromium_tuning() runs
--no-sandbox is normally already there. It is added here too if not, so this
module does not depend on that fix having run first.
"""

from __future__ import annotations

import os
from typing import Callable

from . import bench, desktopfiles
from .system import container_path

Log = Callable[[str], None]

FIREFOX_BIN = "/usr/bin/firefox-esr"
FIREFOX_PREFS_DIR = "/usr/lib/firefox-esr/browser/defaults/preferences"
FIREFOX_VIDEO_PREFS_FILE = f"{FIREFOX_PREFS_DIR}/xlabs-video.js"
FIREFOX_SAFE_PREFS_FILE = f"{FIREFOX_PREFS_DIR}/xlabs-perf.js"
FIREFOX_REDUCED_SECURITY_FILE = f"{FIREFOX_PREFS_DIR}/xlabs-reduced-security.js"

CHROMIUM_BIN = "/usr/bin/chromium"
# Presence of this one flag is enough to tell "tuned" from "untouched" — it
# never appears on an unpatched .desktop file and is always added together
# with the rest.
CHROMIUM_TUNING_MARKER = "--renderer-process-limit=2"

# Firefox scans FIREFOX_PREFS_DIR for default preferences, so a file there
# applies before any profile exists and without locking anything: every
# value below can still be changed in about:config.
FIREFOX_VIDEO_PREFS = """// XLabs — video defaults for proot on Android.
//
// YouTube serves VP9 or AV1 by default. Neither can be hardware decoded in
// this stack: there is no VA-API through proot, so both are decoded on the
// CPU, and that is what makes playback stutter. Turning them off makes
// YouTube fall back to H.264, which is far cheaper to decode.
//
// VirGL does not help here. It accelerates OpenGL — rendering and
// compositing — while the cost of a video is in decoding it.
//
// These are defaults, not locks. Change them in about:config if you want
// AV1 back on a device that can afford it.
pref("media.mediasource.vp9.enabled", false);
pref("media.av1.enabled", false);
"""

FIREFOX_SAFE_PREFS_TEMPLATE = """// XLabs — performance defaults for proot on Android.
//
// Every open/stat/read/write a browser makes goes through proot's ptrace
// intercept, so process count and write frequency matter far more here
// than raw engine speed. None of these cost a feature beyond what they
// say — the reduced-security tier (Fission, Safe Browsing) is a separate,
// explicitly-confirmed file, not this one.
//
// Defaults, not locks — change any of these in about:config.
user_pref("dom.ipc.processCount", 2);
user_pref("dom.ipc.processCount.webIsolated", 1);
user_pref("browser.preferences.defaultPerformanceSettings.enabled", false);
user_pref("browser.sessionstore.interval", 600000);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.cache.disk.enable", false);
user_pref("browser.cache.memory.enable", true);
user_pref("browser.cache.memory.capacity", 131072);
user_pref("toolkit.telemetry.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("dom.w3c_touch_events.enabled", 1);
user_pref("ui.prefersReducedMotion", 1);
user_pref("general.smoothScroll", false);
user_pref("browser.tabs.unloadOnLowMemory", true);
{webrender_line}
"""

FIREFOX_REDUCED_SECURITY_PREFS = """// XLabs — reduced-security performance defaults for proot on Android.
//
// Applied only via Doctor Tools -> Browser -> "Reduce Firefox security
// further", behind an explicit confirmation: both settings below are real
// security reductions, not just behavior changes.
//
// fission.autostart=false removes Firefox's per-site content-process
// isolation — a compromised tab's content process can then see others',
// not just its own. It also unlocks a lower dom.ipc.processCount than
// Fission otherwise permits.
user_pref("fission.autostart", false);
//
// Safe Browsing's phishing/malware blocklists are themselves periodically
// downloaded and written to disk — disabling them removes that traffic,
// but also removes the warning before a known-bad page loads.
user_pref("browser.safebrowsing.malware.enabled", false);
user_pref("browser.safebrowsing.phishing.enabled", false);
"""

# Chromium: not optimizations by themselves like the Firefox prefs above,
# but flags. --no-sandbox and --use-gl=egl are added separately by
# apply_chromium_tuning() because whether they apply depends on state
# (already patched by electron.py, GPU preset measured or not).
CHROMIUM_FLAGS = (
    "--process-per-site",
    "--renderer-process-limit=2",
    "--disable-background-networking",
    "--disable-breakpad",
    "--disable-domain-reliability",
    "--disable-smooth-scrolling",
    "--disable-features=Translate,MediaRouter",
    "--password-store=basic",
)


def _gpu_accelerated() -> bool:
    """Whether a real GPU preset (not software, not unmeasured) is active —
    both gfx.webrender and Chromium's --use-gl=egl only help if virgl/zink
    actually works, and are worse than nothing if the desktop fell back to
    software rendering."""
    profile = bench.load_profile()
    return profile is not None and profile.name != "software"


def _write_prefs_file(target_path: str, body: str, log: Log) -> bool:
    directory = container_path(FIREFOX_PREFS_DIR)
    if not os.path.isdir(directory):
        log(f"  {FIREFOX_PREFS_DIR} does not exist in the container")
        return False
    target = container_path(target_path)
    try:
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
    except OSError as e:
        log(f"  could not write {target_path}: {e}")
        return False
    log(f"  wrote {target_path}")
    return True


def firefox_present() -> bool:
    return os.path.exists(container_path(FIREFOX_BIN))


def firefox_video_prefs_ok() -> bool:
    return os.path.exists(container_path(FIREFOX_VIDEO_PREFS_FILE))


def apply_firefox_video_prefs(log: Log) -> bool:
    if not _write_prefs_file(FIREFOX_VIDEO_PREFS_FILE, FIREFOX_VIDEO_PREFS, log):
        return False
    log("  restart Firefox for it to take effect")
    return True


def firefox_safe_tuning_ok() -> bool:
    return os.path.exists(container_path(FIREFOX_SAFE_PREFS_FILE))


def apply_firefox_safe_tuning(log: Log) -> bool:
    webrender_line = (
        'user_pref("gfx.webrender.all", true);'
        if _gpu_accelerated()
        else 'user_pref("gfx.webrender.software", true);'
    )
    body = FIREFOX_SAFE_PREFS_TEMPLATE.format(webrender_line=webrender_line)
    if not _write_prefs_file(FIREFOX_SAFE_PREFS_FILE, body, log):
        return False
    log("  restart Firefox for it to take effect")
    return True


def firefox_reduced_security_ok() -> bool:
    return os.path.exists(container_path(FIREFOX_REDUCED_SECURITY_FILE))


def apply_firefox_reduced_security(log: Log) -> bool:
    if not _write_prefs_file(
        FIREFOX_REDUCED_SECURITY_FILE, FIREFOX_REDUCED_SECURITY_PREFS, log
    ):
        return False
    log("  restart Firefox for it to take effect")
    return True


def chromium_present() -> bool:
    return os.path.exists(container_path(CHROMIUM_BIN))


def _chromium_desktop_file() -> tuple[str, str] | None:
    root = container_path("/")
    return desktopfiles.find_desktop_file_for_binary(root, {"chromium", "chromium-browser"})


def chromium_tuning_ok() -> bool | None:
    """True/False once Chromium's .desktop entry is found, None if there is
    nothing to check yet — no container, no Chromium, or no launcher for it
    to appear in."""
    found = _chromium_desktop_file()
    if found is None:
        return None
    _, content = found
    return desktopfiles.desktop_exec_has(content, CHROMIUM_TUNING_MARKER)


def apply_chromium_tuning(log: Log) -> bool:
    found = _chromium_desktop_file()
    if found is None:
        log("  no Chromium .desktop entry found in the container")
        return False
    path, content = found
    binary = desktopfiles.desktop_exec_binary(content)
    assert binary is not None

    flags = list(CHROMIUM_FLAGS)
    if not desktopfiles.desktop_exec_has(content, "--no-sandbox"):
        flags.insert(0, "--no-sandbox")
    if _gpu_accelerated():
        flags.append("--use-gl=egl")

    missing = [f for f in flags if not desktopfiles.desktop_exec_has(content, f)]
    if not missing:
        log("  already tuned")
        return True

    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(desktopfiles.patch_desktop_exec(content, binary, " ".join(missing)))
    except OSError as e:
        log(f"  could not write {path}: {e}")
        return False

    log(f"  {os.path.basename(path)} -> {' '.join(missing)}")
    log("  restart Chromium for it to take effect")
    return True
