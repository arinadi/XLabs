"""Desktop lifecycle: PulseAudio → virgl → X11 → Xfce4, and the reverse on stop.

Every function here blocks and takes a `log` callback so the caller decides
where output goes — a Textual RichLog, or plain print from the installer.
"""

import os
import socket as sock
import subprocess
import time

from .const import CONTAINER_NAME, PROOT_DIR, REPO_DIR, TMPDIR
from .system import run_cmd

ANGLE_DIR = "/data/data/com.termux/files/usr/opt/angle-android"
XFCE_LOG = os.path.join(REPO_DIR, "xfce4.log")

# Matches every process the desktop stack can leave behind.
SURVIVOR_PATTERN = (
    "xfce4|xfwm4|xfdesktop|thunar|pulseaudio|"
    "termux-x11|termux.x11|dbus-|startxfce4|proot.*arinanolabs"
)


def _noop(_message: str) -> None:
    pass


def is_running() -> bool:
    """True when an Xfce4 session is alive."""
    rc, _ = run_cmd("pgrep -f 'xfce4-session|startxfce4'")
    return rc == 0


# ── Stop ───────────────────────────────────────────────────


def stop_desktop(log=_noop) -> bool:
    """Stop the desktop and clean up every socket and runtime dir it left."""
    # Phase 1: kill the Android-side X server first, so clients lose their
    # display before we start killing them.
    log("Force-stopping Termux:X11 app...")
    run_cmd("am force-stop com.termux.x11 2>/dev/null")

    # Phase 2: let the well-behaved ones exit cleanly.
    log("Signalling X11 and PulseAudio...")
    for pat in ("termux-x11", "termux.x11", "pulseaudio"):
        run_cmd(f"pkill -f '{pat}' 2>/dev/null")

    # Phase 3: force-kill, leaf apps before the session that supervises them.
    log("Killing desktop processes...")
    force_kill = [
        "termux-x11", "termux.x11",
        "thunar", "xfdesktop4", "xfce4-panel", "xfce4-terminal",
        "xfce4-appfinder", "xfce4-settingsd", "xfce4-power-manager",
        "xfwm4", "xfce4-session",
        "dbus-daemon", "dbus-launch",
        "virgl_test_server", "pulseaudio", "startxfce4",
        "proot.*arinanolabs",
    ]
    for pat in force_kill:
        run_cmd(f"pkill -9 -f '{pat}' 2>/dev/null")

    for mod in ("module-null-sink", "module-native-protocol-tcp"):
        run_cmd(f"pactl unload-module {mod} 2>/dev/null")

    # Phase 4: verify, and re-kill whatever outlived the first pass.
    time.sleep(1)
    rc, _ = run_cmd(f"pgrep -f '{SURVIVOR_PATTERN}'")
    if rc == 0:
        log("Survivors found, killing again...")
        run_cmd(f"pkill -9 -f '{SURVIVOR_PATTERN}' 2>/dev/null")
        time.sleep(0.5)

    # Phase 5: host-side files. Remove the whole socket dir, not its contents,
    # or a stale .X11-unix keeps the next termux-x11 from binding.
    log("Cleaning Termux sockets...")
    run_cmd(f"rm -rf {TMPDIR}/.X11-unix 2>/dev/null")
    run_cmd(f"rm -f {TMPDIR}/.X*-lock 2>/dev/null")
    run_cmd(f"rm -f {TMPDIR}/dbus-* 2>/dev/null")
    run_cmd(f"rm -rf {TMPDIR}/runtime-* {TMPDIR}/pulse* 2>/dev/null")

    # Phase 6: proot-side residue, from inside the container and again from
    # the host in case the container can no longer be entered.
    log("Cleaning container session residue...")
    run_cmd(
        f"proot-distro login {CONTAINER_NAME} -- bash -c "
        "'rm -rf /tmp/xdg-* /tmp/dbus-* /tmp/.xfsm-ICE-* "
        "/tmp/.X11-unix/* /tmp/runtime-* "
        "/home/admin/.cache/sessions/* "
        "/home/admin/.ICEauthority /home/admin/.Xauthority 2>/dev/null'"
    )
    proot_tmp = os.path.join(PROOT_DIR, "rootfs/tmp")
    run_cmd(f"rm -rf {proot_tmp}/.X11-unix {proot_tmp}/.X*-lock 2>/dev/null")
    run_cmd(f"rm -f {proot_tmp}/dbus-* {proot_tmp}/.dbus* 2>/dev/null")
    run_cmd(f"rm -rf {proot_tmp}/runtime-* {proot_tmp}/xdg-* {proot_tmp}/.xfsm-ICE-* 2>/dev/null")
    proot_home = os.path.join(PROOT_DIR, "rootfs/home/admin")
    run_cmd(f"rm -f {proot_home}/.ICEauthority {proot_home}/.Xauthority 2>/dev/null")
    run_cmd(f"rm -rf {proot_home}/.cache/sessions 2>/dev/null")

    run_cmd("termux-wake-unlock 2>/dev/null")
    log("Stopped.")
    return True


# ── Start steps ────────────────────────────────────────────


def acquire_wake_lock(log=_noop) -> bool:
    """Hold a Termux wake lock so Android does not freeze the session."""
    rc, _ = run_cmd("termux-wake-lock 2>/dev/null")
    if rc != 0:
        log("  wake lock unavailable (install Termux:API to keep sessions alive)")
        return False
    return True


def start_pulseaudio(log=_noop) -> bool:
    run_cmd("pulseaudio --kill 2>/dev/null")
    time.sleep(0.5)
    run_cmd(f"rm -rf {TMPDIR}/pulse* 2>/dev/null")

    rc, out = run_cmd("pulseaudio --start --exit-idle-time=-1 2>&1")
    if rc != 0 and "already running" not in out.lower():
        log(f"  {out.strip()}")
        return False
    return True


def load_audio_modules(log=_noop) -> bool:
    run_cmd(
        "pactl load-module module-native-protocol-tcp "
        "auth-ip-acl=127.0.0.1 auth-anonymous=1 port=4713 2>/dev/null"
    )
    # Android-specific sinks; absent on most builds, so failure is expected.
    run_cmd("pactl load-module module-aaudio-sink 2>/dev/null")
    run_cmd("pactl load-module module-sles-sink 2>/dev/null")
    return True


def start_virgl(log=_noop) -> bool:
    """Start the first virgl renderer that exists. No GPU vendor detection."""
    rc, _ = run_cmd("command -v virgl_test_server_android")
    if rc == 0:
        subprocess.Popen(
            "virgl_test_server_android", shell=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        log("  using virgl_test_server_android")
        return True

    for backend in ("vulkan-null", "vulkan"):
        path = f"{ANGLE_DIR}/{backend}"
        if os.path.exists(path):
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = path
            subprocess.Popen(
                "virgl_test_server --use-egl-surfaceless --use-gles",
                shell=True, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            log(f"  using ANGLE {backend}")
            return True

    log("  no virgl renderer found, falling back to software rendering")
    return False


def start_x11(log=_noop) -> bool:
    run_cmd("pkill -9 -f termux-x11 2>/dev/null")
    time.sleep(0.5)
    run_cmd(f"rm -f {TMPDIR}/.X*-lock {TMPDIR}/.X11-unix/X* 2>/dev/null")
    time.sleep(0.5)

    subprocess.Popen(
        "termux-x11 :0 -ac", shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(3)

    rc, _ = run_cmd("pgrep -f termux-x11")
    if rc != 0 or not os.path.exists(f"{TMPDIR}/.X11-unix/X0"):
        log("  termux-x11 failed to start")
        return False

    subprocess.Popen(
        "am start -n com.termux.x11/com.termux.x11.MainActivity", shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return True


def wait_for_x11(log=_noop) -> bool:
    """Wait until the socket actually accepts a connection, not just exists."""
    socket_path = f"{TMPDIR}/.X11-unix/X0"
    for i in range(50):
        if os.path.exists(socket_path):
            try:
                s = sock.socket(sock.AF_UNIX, sock.SOCK_STREAM)
                s.connect(socket_path)
                s.close()
                log(f"  ready in {(i + 1) * 100}ms")
                return True
            except OSError:
                pass
        time.sleep(0.1)

    log("  socket timeout, continuing anyway")
    return True


def start_xfce4(log=_noop) -> bool:
    exports = "DISPLAY=:0 PULSE_SERVER=tcp:127.0.0.1:4713 NO_AT_BRIDGE=1"

    # 'su admin' without '-' so .bashrc cannot clobber XDG_RUNTIME_DIR, which
    # dbus needs to be mode 0700.
    inner = (
        f"export {exports} && "
        "XDG=/tmp/runtime-$$ && mkdir -p $XDG && chmod 0700 $XDG && "
        "export XDG_RUNTIME_DIR=$XDG && "
        "exec startxfce4"
    )
    cmd = (
        f"proot-distro login {CONTAINER_NAME} --shared-x11 -- "
        f"su admin -c '{inner}'"
    )

    os.makedirs(os.path.dirname(XFCE_LOG), exist_ok=True)
    with open(XFCE_LOG, "w") as f:
        subprocess.Popen(cmd, shell=True, stdout=f, stderr=f)

    time.sleep(5)

    if is_running():
        return True

    log("  session failed to start; first lines of xfce4.log:")
    try:
        with open(XFCE_LOG) as f:
            for line in f.read().strip().splitlines()[:5]:
                log(f"    {line}")
    except OSError:
        log("    (log unreadable)")
    return False


START_STEPS = [
    ("Acquiring wake lock", acquire_wake_lock),
    ("Starting PulseAudio", start_pulseaudio),
    ("Loading audio modules", load_audio_modules),
    ("Starting virgl renderer", start_virgl),
    ("Starting X11 server", start_x11),
    ("Waiting for X11 socket", wait_for_x11),
    ("Launching Xfce4 desktop", start_xfce4),
]


def start_desktop(log=_noop) -> bool:
    """Run the full start sequence, stopping a stale session first."""
    if is_running():
        log("Desktop already running — stopping it first.\n")
        stop_desktop(log)
        log("")

    for name, step in START_STEPS:
        log(f"{name}...")
        try:
            ok = step(log)
        except Exception as e:  # noqa: BLE001 - shown to the user as log text
            log(f"  failed: {e}")
            ok = False
        log("  ok" if ok else "  warning")

    return is_running()
