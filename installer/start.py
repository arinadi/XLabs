"""Start desktop (PulseAudio → virgl → X11 → MATE)."""

import os
import subprocess
import time

from .ui import console, run_cmd, run_cmd_stream, PROOT_DIR
from .gpu import detect_gpu, GPU_CONFIGS


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
        ("Launching MATE desktop", start_mate),
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

    # Kill all at once
    run_cmd("pkill -9 -f mate-session 2>/dev/null")
    run_cmd("pkill -9 -f marco 2>/dev/null")
    run_cmd("pkill -9 -f mate-panel 2>/dev/null")
    run_cmd("pkill -9 -f dbus-launch 2>/dev/null")
    run_cmd("pkill -9 -f virgl_test_server 2>/dev/null")
    run_cmd("pkill -9 -f termux-x11 2>/dev/null")
    run_cmd("pkill -9 -f pulseaudio 2>/dev/null")
    run_cmd("pkill -9 -f pactl 2>/dev/null")

    # Cleanup temp files
    tmpdir = os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")
    for f in [".X0-lock", ".X11-unix"]:
        run_cmd(f"rm -rf {tmpdir}/{f} 2>/dev/null")

    print("  All processes killed.")
    return True

    print("\n  Desktop stopped.")
    return True


def is_running() -> bool:
    """Check if MATE session is running."""
    rc, _ = run_cmd("pgrep -f mate-session")
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
    subprocess.Popen("termux-x11 :0 -ac", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    # Auto-open X11 app
    subprocess.Popen("am start -n com.termux.x11/com.termux.x11.MainActivity", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def wait_for_x11() -> bool:
    """Wait for X11 socket to be ready."""
    tmpdir = os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")
    socket_path = f"{tmpdir}/.X11-unix/X0"

    for i in range(50):  # Wait up to 5 seconds
        if os.path.exists(socket_path):
            console.print(f"    [green]✓ X11 ready ({(i+1)*100}ms)[/green]")
            return True
        time.sleep(0.1)

    console.print("    [yellow]⚠ X11 socket timeout, proceeding anyway[/yellow]")
    return True


def start_mate() -> bool:
    """Start MATE session in proot."""
    gpu = detect_gpu()
    env_vars = {
        "DISPLAY": ":0",
        "PULSE_SERVER": "tcp:127.0.0.1:4713",
        "NO_AT_BRIDGE": "1",
        "LIBGL_ALWAYS_SOFTWARE": "0",
    }

    # Add GPU-specific env vars
    env_vars.update(gpu.mesa_config)

    env_str = " ".join(f"export {k}={v}" for k, v in env_vars.items())

    # Start in background, capture output for debugging
    cmd = (
        f"proot-distro login arinanolabs --isolated --bind /tmp:/tmp -- su - admin -c '"
        f"{env_str} && "
        f"rm -f /tmp/dbus-* 2>/dev/null && "
        f"dbus-launch --exit-with-session mate-session"
        f"'"
    )

    # Log to file for debugging
    log_file = os.path.expanduser("~/arinanoLabs/mate.log")
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
    rc, _ = run_cmd("pgrep -f mate-session")
    if rc == 0:
        print("    MATE session running")
        return True
    else:
        print("    MATE session failed to start")
        print(f"    Check log: {log_file}")
        return False
