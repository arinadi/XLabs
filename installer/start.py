"""Desktop lifecycle: PulseAudio → virgl → X11 → Xfce4, and the reverse on stop.

Every function here blocks and takes a `log` callback so the caller decides
where output goes — a Textual RichLog, or plain print from the installer.
"""

import os
import socket as sock
import subprocess
import time

from .const import ADMIN_USER, CONTAINER_NAME, PROOT_DIR, REPO_DIR, TMPDIR
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


# Run inside the container as the admin user. Written to the rootfs and
# executed by path so no quoting has to survive the trip through proot-distro.
#
# The D-Bus wrapper matters: startxfce4 only starts a bus on its Wayland
# branch. With DISPLAY already set it prints "X server already running",
# sets prog=/bin/sh and hands off to xinitrc — so if nothing brings a session
# bus, xfce4-session has none. Every reference setup wraps the session in
# dbus-launch --exit-with-session for exactly this reason.
SESSION_SCRIPT = r"""#!/bin/bash
export DISPLAY=:0
export PULSE_SERVER=tcp:127.0.0.1:4713
export NO_AT_BRIDGE=1

export XDG_RUNTIME_DIR="/tmp/runtime-$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"

echo "starting as $(whoami), DISPLAY=$DISPLAY, XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"

if [ -z "$DBUS_SESSION_BUS_ADDRESS" ] && command -v dbus-launch >/dev/null 2>&1; then
    echo "wrapping the session in dbus-launch"
    exec dbus-launch --exit-with-session startxfce4
fi

echo "using the existing session bus: ${DBUS_SESSION_BUS_ADDRESS:-none}"
exec startxfce4
"""

SESSION_SCRIPT_NAME = "arinanolabs-session.sh"


def start_xfce4(log=_noop) -> bool:
    # --user admin rather than `su admin -c`: proot-distro sets HOME, USER and
    # the working directory itself, and su inside proot's faked root is where
    # this has repeatedly gone wrong.
    # --shared-tmp rather than --shared-x11: every reference setup uses it, and
    # it exposes the whole Termux tmp, which is where the X socket, the D-Bus
    # socket and XDG_RUNTIME_DIR all live.
    if not _write_container_script(SESSION_SCRIPT_NAME, SESSION_SCRIPT):
        log("  could not write the session script")
        return False

    cmd = (
        f"proot-distro login {CONTAINER_NAME} --user {ADMIN_USER} --shared-tmp "
        f"-- bash /tmp/{SESSION_SCRIPT_NAME}"
    )

    log(f"  {cmd}")

    os.makedirs(os.path.dirname(XFCE_LOG), exist_ok=True)
    with open(XFCE_LOG, "w") as f:
        subprocess.Popen(cmd, shell=True, stdout=f, stderr=f)

    # Poll rather than sleeping a fixed five seconds. A cold start on a slow
    # phone routinely takes longer, and declaring failure early sends people
    # debugging a desktop that was merely still coming up.
    for waited in range(1, 31):
        time.sleep(1)
        if is_running():
            log(f"  session up after {waited}s")
            return True
        if waited in (5, 10, 20):
            log(f"  still waiting ({waited}s)...")

    log("  no xfce4-session after 30s")
    return False


# Written into the container's filesystem and run by path. Passing this as a
# quoted -c argument through proot-distro does not survive: an earlier version
# used `tr '\n' ' '` inside an already single-quoted host string and the probe
# died with "unexpected EOF", taking the most useful half of the report with it.
CONTAINER_PROBE = r"""#!/bin/bash
echo "whoami:        $(whoami)"
echo "admin user:    $(id admin 2>&1)"
echo "startxfce4:    $(command -v startxfce4 || echo MISSING)"
echo "xfce4-session: $(command -v xfce4-session || echo MISSING)"
echo "dbus-launch:   $(command -v dbus-launch || echo MISSING)"
echo "xset:          $(command -v xset || echo MISSING)"
echo "DBUS address:  ${DBUS_SESSION_BUS_ADDRESS:-(unset)}"
echo "socket dir:"
ls -la /tmp/.X11-unix 2>&1 | sed 's/^/  /'

export DISPLAY=:0
echo "xset q:"
xset q 2>&1 | head -3 | sed 's/^/  /'

echo "--- xfce4-session foreground run, 8s ---"
su admin -c '
export DISPLAY=:0
export XDG_RUNTIME_DIR=/tmp/runtime-probe
mkdir -p $XDG_RUNTIME_DIR
chmod 0700 $XDG_RUNTIME_DIR
timeout 8 xfce4-session
' >/tmp/arinanolabs-session.out 2>&1
# Capture the session's own status, not sed's: piping straight into head
# reported the pipeline's exit code and always said 0.
status=$?
head -25 /tmp/arinanolabs-session.out | sed 's/^/  /'
echo "--- exit: $status (124 = still alive when the 8s timeout fired) ---"
"""


def _write_container_script(name: str, content: str) -> bool:
    """Place a script where the container will see it at /tmp/<name>.

    Written to the Termux tmp, not the container rootfs: --shared-tmp binds
    the Termux tmp over /tmp, so anything left in rootfs/tmp is hidden the
    moment the session starts.
    """
    try:
        os.makedirs(TMPDIR, exist_ok=True)
        path = os.path.join(TMPDIR, name)
        with open(path, "w", newline="\n") as f:
            f.write(content)
        os.chmod(path, 0o755)
        return True
    except OSError:
        return False


def _run_container_probe() -> tuple[int, str]:
    """Run the probe script inside the container.

    The flags must match how the desktop is actually started, or the probe
    diagnoses its own environment instead. An earlier version logged in
    without sharing the X socket at all and duly reported "unable to open
    display" — indistinguishable from the failure it exists to explain.
    """
    if not _write_container_script("arinanolabs-probe.sh", CONTAINER_PROBE):
        return 1, "could not write the probe script"

    return run_cmd(
        f"proot-distro login {CONTAINER_NAME} --shared-tmp "
        "-- bash /tmp/arinanolabs-probe.sh",
        timeout=120,
    )


def collect_diagnostics(log=_noop) -> None:
    """Gather everything needed to explain why the desktop never appeared.

    The usual symptom is an X cursor on an empty root window, which means the
    server is up and nothing connected to it. That splits into host-side
    causes (no server, no socket) and container-side ones (no session binary,
    no admin user, or the display not reachable through the --shared-x11 bind
    mount). The `xset q` probe below is the one that separates them: if it
    answers from inside the container, the display path is fine and the fault
    is in the session itself.
    """
    log("")
    log("── Host ──────────────────────────────────────")
    host_probes = (
        ("termux-x11", "pgrep -af termux-x11"),
        ("X11 socket", f"ls -la {TMPDIR}/.X11-unix 2>&1"),
        ("X lock files", f"ls -la {TMPDIR}/.X*-lock 2>&1"),
        ("PulseAudio", "pgrep -af pulseaudio"),
        ("virgl", "pgrep -af virgl_test_server"),
        ("proot sessions", f"pgrep -af 'proot.*{CONTAINER_NAME}'"),
        ("DISPLAY", "echo \"${DISPLAY:-(unset)}\""),
    )
    for label, cmd in host_probes:
        _, out = run_cmd(cmd)
        text = out.strip() or "(nothing)"
        log(f"{label}:")
        for line in text.splitlines()[:8]:
            log(f"  {line}")

    log("")
    log("── Container ─────────────────────────────────")
    rc, out = _run_container_probe()
    text = out.strip()
    if not text:
        log(f"  could not enter the container (exit {rc})")
    for line in text.splitlines()[:40]:
        log(f"  {line}")

    log("")
    log("── xfce4.log ─────────────────────────────────")
    try:
        with open(XFCE_LOG) as f:
            content = f.read().strip()
    except OSError as e:
        content = f"(unreadable: {e})"
    if not content:
        content = "(empty — the session wrote nothing at all)"
    for line in content.splitlines()[-40:]:
        log(f"  {line}")

    log("")
    log("[dim]Reading this:[/dim]")
    log("[dim]  xset q answers        -> the display path works; the fault is[/dim]")
    log("[dim]                           in the session, see the foreground run[/dim]")
    log("[dim]  unable to open display -> the socket is not reaching the[/dim]")
    log("[dim]                           container; --shared-x11 or cleanup[/dim]")
    log("[dim]  'Killed' and nothing else -> Android killed the process; see[/dim]")
    log("[dim]                           the phantom process killer note in[/dim]")
    log("[dim]                           the README[/dim]")


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

    if is_running():
        return True

    log("")
    log("[bold]Desktop did not come up — collecting diagnostics[/bold]")
    collect_diagnostics(log)
    return False
