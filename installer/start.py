"""Start desktop (PulseAudio → virgl → X11 → Xfce4)."""

import os
import subprocess
import time

from .ui import console, run_cmd, run_cmd_stream, PROOT_DIR


def start_desktop() -> bool:
    """Start the full desktop stack."""
    # Check if already running
    if is_running():
        print("  Desktop is already running!")
        return True

    steps = [
        ("Starting PulseAudio", start_pulseaudio),
        ("Loading audio modules", load_audio_modules),
        ("Starting virgl renderer", start_virgl),
        ("Starting X11 server", start_x11),
        ("Waiting for X11 socket", wait_for_x11),
        ("Launching Xfce4 desktop", start_xfce4),
    ]

    for name, step_fn in steps:
        print(f"  -> {name}...")
        try:
            success = step_fn()
            if not success:
                print(f"    Warning")
        except Exception as e:
            print(f"    Failed: {e}")

    print()
    print("  Desktop started!")
    print("  Open Termux:X11 app to see your desktop.")
    return True


def stop_desktop() -> bool:
    """Stop all desktop processes."""
    print("\n  Stopping desktop...\n")

    # Kill processes — order matters: apps first, then infrastructure
    for name, cmd in [
        ("xfce4-session", "pkill -9 -f xfce4-session 2>/dev/null"),
        ("xfce4-panel", "pkill -9 -f xfce4-panel 2>/dev/null"),
        ("xfwm4", "pkill -9 -f xfwm4 2>/dev/null"),
        ("thunar", "pkill -9 -f thunar 2>/dev/null"),
        ("dbus-launch", "pkill -9 -f dbus-launch 2>/dev/null"),
        ("virgl", "pkill -9 -f virgl_test_server 2>/dev/null"),
        ("termux-x11", "pkill -9 -f termux-x11 2>/dev/null"),
    ]:
        rc, out = run_cmd(cmd)
        status = "killed" if rc == 0 else "not running"
        print(f"    {name}: {status}")

    # Unload PulseAudio modules
    for mod in ["module-null-sink", "module-native-protocol-tcp"]:
        rc, out = run_cmd(f"pactl unload-module {mod} 2>/dev/null")
        print(f"    pulseaudio {mod}: {'unloaded' if rc == 0 else 'not loaded'}")

    rc, out = run_cmd("pkill -9 -f pulseaudio 2>/dev/null")
    print(f"    pulseaudio: {'killed' if rc == 0 else 'not running'}")

    # Kill any leftover proot wrapper processes
    rc, out = run_cmd("pkill -9 -f 'proot.*arinanolabs' 2>/dev/null")
    print(f"    proot wrapper: {'killed' if rc == 0 else 'not running'}")

    # Kill orphaned dbus-daemon processes
    rc, out = run_cmd("pkill -9 -f dbus-daemon 2>/dev/null")
    print(f"    dbus-daemon: {'killed' if rc == 0 else 'not running'}")

    # Wait for processes to actually die
    time.sleep(1)

    # Cleanup X11 lock files and socket (keep the directory itself)
    tmpdir = os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")
    run_cmd(f"rm -f {tmpdir}/.X*-lock {tmpdir}/.X11-unix/X* 2>/dev/null")
    print(f"    rm X11 locks+socket: ok")

    # Cleanup stale dbus sockets in Termux TMPDIR
    rc, _ = run_cmd(f"rm -f {tmpdir}/dbus-* 2>/dev/null")
    print(f"    rm dbus sockets (termux): {'ok' if rc == 0 else 'failed'}")

    # Cleanup stale runtime dirs in Termux TMPDIR
    rc, _ = run_cmd(f"rm -rf {tmpdir}/runtime-* 2>/dev/null")
    print(f"    rm runtime dirs (termux): {'ok' if rc == 0 else 'failed'}")

    # Cleanup inside proot container's /tmp (dbus sockets + runtime dirs)
    proot_tmp = os.path.join(PROOT_DIR, "rootfs/tmp")
    rc, _ = run_cmd(f"rm -f {proot_tmp}/dbus-* 2>/dev/null")
    print(f"    rm dbus sockets (proot): {'ok' if rc == 0 else 'failed'}")
    rc, _ = run_cmd(f"rm -rf {proot_tmp}/runtime-* 2>/dev/null")
    print(f"    rm runtime dirs (proot): {'ok' if rc == 0 else 'failed'}")

    # Verify all processes are dead
    rc, out = run_cmd("pgrep -f 'xfce4-session|xfwm4|pulseaudio|termux-x11|proot.*arinanolabs'")
    if rc == 0:
        print(f"\n  ⚠ Processes still alive: {out.strip()}")
        run_cmd("pkill -9 -f xfce4-session 2>/dev/null")
        run_cmd("pkill -9 -f pulseaudio 2>/dev/null")
        run_cmd("pkill -9 -f termux-x11 2>/dev/null")
        run_cmd("pkill -9 -f 'proot.*arinanolabs' 2>/dev/null")
        time.sleep(0.5)
    else:
        print("\n  ✓ All processes stopped.")

    return True


def is_running() -> bool:
    """Check if Xfce4 session is running."""
    rc, _ = run_cmd("pgrep -f 'xfce4-session|startxfce4'")
    return rc == 0


# ── Internal Functions ─────────────────────────────────────

def start_pulseaudio() -> bool:
    """Start PulseAudio server."""
    # Kill existing
    run_cmd("pulseaudio --kill 2>/dev/null")
    time.sleep(0.5)

    # Remove stale socket
    tmpdir = os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")
    run_cmd(f"rm -rf {tmpdir}/pulse* 2>/dev/null")

    # Start fresh
    rc, out = run_cmd("pulseaudio --start --exit-idle-time=-1 2>&1")
    if rc != 0 and "already running" not in out.lower():
        print(f"    PulseAudio warning: {out.strip()}")
    return True


def load_audio_modules() -> bool:
    """Load audio sink modules."""
    # Load modules, ignore errors
    run_cmd("pactl load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1 auth-anonymous=1 port=4713 2>/dev/null")
    # Try Android-specific modules (may not exist)
    run_cmd("pactl load-module module-aaudio-sink 2>/dev/null")
    run_cmd("pactl load-module module-sles-sink 2>/dev/null")
    return True


def start_virgl() -> bool:
    """Start virgl renderer (auto-detect path)."""
    # Try Android path first
    rc, _ = run_cmd("which virgl_test_server_android 2>/dev/null")
    if rc == 0:
        subprocess.Popen("virgl_test_server_android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    # Try ANGLE path
    angle_dir = "/data/data/com.termux/files/usr/opt/angle-android"
    if os.path.exists(f"{angle_dir}/vulkan-null"):
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = f"{angle_dir}/vulkan-null"
        subprocess.Popen("virgl_test_server --use-egl-surfaceless --use-gles", shell=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    if os.path.exists(f"{angle_dir}/vulkan"):
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = f"{angle_dir}/vulkan"
        subprocess.Popen("virgl_test_server --use-egl-surfaceless --use-gles", shell=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    # Fallback - no virgl
    print("    No virgl renderer found, using software rendering")
    return False


def start_x11() -> bool:
    """Start Termux:X11 server."""
    # Kill any stale termux-x11 and clean ALL lock/socket files
    run_cmd("pkill -9 -f termux-x11 2>/dev/null")
    time.sleep(0.5)
    tmpdir = os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")
    # Remove ALL X lock files (X0-lock, X1-lock, etc.) and socket
    run_cmd(f"rm -f {tmpdir}/.X*-lock {tmpdir}/.X11-unix/X* 2>/dev/null")
    time.sleep(0.5)

    subprocess.Popen("termux-x11 :0 -ac", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

    # Verify termux-x11 is actually running AND socket exists
    rc, _ = run_cmd("pgrep -f termux-x11")
    socket_path = f"{tmpdir}/.X11-unix/X0"
    if rc != 0 or not os.path.exists(socket_path):
        console.print("    [red]✗ termux-x11 failed to start[/red]")
        return False

    # Auto-open X11 app
    subprocess.Popen("am start -n com.termux.x11/com.termux.x11.MainActivity", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def wait_for_x11() -> bool:
    """Wait for X11 socket to be ready and accepting connections."""
    import socket as sock
    tmpdir = os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")
    socket_path = f"{tmpdir}/.X11-unix/X0"

    for i in range(50):  # Wait up to 5 seconds
        if os.path.exists(socket_path):
            # Verify actual connection (not just stale socket file)
            try:
                s = sock.socket(sock.AF_UNIX, sock.SOCK_STREAM)
                s.connect(socket_path)
                s.close()
                console.print(f"    [green]✓ X11 ready ({(i+1)*100}ms)[/green]")
                return True
            except (ConnectionRefusedError, OSError):
                pass
        time.sleep(0.1)

    console.print("    [yellow]⚠ X11 socket timeout, proceeding anyway[/yellow]")
    return True


def start_xfce4() -> bool:
    """Start Xfce4 session in proot."""
    env_vars = {
        "DISPLAY": ":0",
        "PULSE_SERVER": "tcp:127.0.0.1:4713",
        "NO_AT_BRIDGE": "1",
    }

    exports = " ".join(f"{k}={v}" for k, v in env_vars.items())

    # Use 'su admin' (no -) to avoid .bashrc overriding XDG_RUNTIME_DIR
    # Create proper XDG_RUNTIME_DIR (mode 0700) for dbus
    inner_cmd = (
        f"export {exports} && "
        f"XDG=/tmp/runtime-$$ && mkdir -p $XDG && chmod 0700 $XDG && "
        f"export XDG_RUNTIME_DIR=$XDG && "
        f"exec startxfce4"
    )

    # Start in background
    cmd = (
        f"proot-distro login arinanolabs --shared-x11 -- "
        f"su admin -c '{inner_cmd}'"
    )

    # Log to file for debugging
    log_file = os.path.expanduser("~/arinanoLabs/xfce4.log")
    with open(log_file, "w") as f:
        subprocess.Popen(cmd, shell=True, stdout=f, stderr=f)

    time.sleep(5)

    # Check log for errors
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            log = f.read()
        if log.strip():
            for line in log.strip().split("\n")[:5]:
                print(f"    {line}")

    # Verify
    rc, _ = run_cmd("pgrep -f 'xfce4-session|startxfce4'")
    if rc == 0:
        print("    Xfce4 session running")
        return True
    else:
        print("    Xfce4 session failed to start")
        print(f"    Check log: {log_file}")
        return False
