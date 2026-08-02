"""Start desktop (PulseAudio → virgl → X11 → MATE)."""

import os
import subprocess
import time

from .ui import console, run_cmd, run_cmd_stream, PROOT_DIR
from .gpu import detect_gpu, GPU_CONFIGS


def start_desktop() -> bool:
    """Start the full desktop stack."""
    console.print("\n[bold]Starting arinanoLabs desktop...[/bold]\n")

    # Check if already running
    if is_running():
        console.print("  [yellow]Desktop is already running![/yellow]")
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
        console.print(f"  [cyan]→[/cyan] {name}...")
        try:
            success = step_fn()
            if not success:
                console.print(f"    [yellow]⚠ Warning[/yellow]")
        except Exception as e:
            console.print(f"    [red]✗ {e}[/red]")

    console.print("\n[green]✓ Desktop started![/green]")
    console.print("  Open Termux:X11 app to see your desktop.\n")
    return True


def stop_desktop() -> bool:
    """Stop all desktop processes."""
    console.print("\n[bold]Stopping arinanoLabs desktop...[/bold]\n")

    processes = [
        "mate-session",
        "marco",
        "mate-panel",
        "dbus-launch",
        "virgl_test_server",
        "termux-x11",
        "pulseaudio",
    ]

    for proc in processes:
        rc, _ = run_cmd(f"pkill -f '{proc}' 2>/dev/null")
        if rc == 0:
            console.print(f"  [dim]Stopped {proc}[/dim]")

    # Force kill remaining
    run_cmd("pkill -9 -f 'mate-session' 2>/dev/null")
    run_cmd("pkill -9 -f 'virgl_test_server' 2>/dev/null")

    # Cleanup temp files
    tmpdir = os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")
    for f in [".X0-lock", ".X11-unix"]:
        run_cmd(f"rm -rf {tmpdir}/{f} 2>/dev/null")

    console.print("\n[green]✓ Desktop stopped.[/green]\n")
    return True


def is_running() -> bool:
    """Check if MATE session is running."""
    rc, _ = run_cmd("pgrep -f mate-session")
    return rc == 0


# ── Internal Functions ─────────────────────────────────────

def start_pulseaudio() -> bool:
    """Start PulseAudio server."""
    run_cmd("pulseaudio --kill 2>/dev/null")  # Kill existing
    time.sleep(0.3)
    rc = run_cmd_stream("pulseaudio --start --exit-idle-time=-1 2>&1")
    return rc == 0


def load_audio_modules() -> bool:
    """Load audio sink modules."""
    run_cmd_stream("pactl load-module module-aaudio-sink 2>&1")
    run_cmd_stream("pactl load-module module-sles-sink 2>&1")
    run_cmd_stream("pactl load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1 auth-anonymous=1 port=4713 2>&1")
    return True


def start_virgl() -> bool:
    """Start virgl renderer (auto-detect path)."""
    # Try Android path first
    rc = run_cmd_stream("which virgl_test_server_android 2>&1")
    if rc == 0:
        run_cmd_stream("virgl_test_server_android &")
        return True

    # Try ANGLE path
    angle_dir = "/data/data/com.termux/files/usr/opt/angle-android"
    if os.path.exists(f"{angle_dir}/vulkan-null"):
        run_cmd_stream(f"LD_LIBRARY_PATH={angle_dir}/vulkan-null virgl_test_server --use-egl-surfaceless --use-gles &")
        return True

    if os.path.exists(f"{angle_dir}/vulkan"):
        run_cmd_stream(f"LD_LIBRARY_PATH={angle_dir}/vulkan virgl_test_server --use-egl-surfaceless --use-gles &")
        return True

    # Fallback - no virgl
    console.print("    [dim]No virgl renderer found, using software rendering[/dim]")
    return False


def start_x11() -> bool:
    """Start Termux:X11 server."""
    rc = run_cmd_stream("termux-x11 :0 -ac 2>&1")
    time.sleep(2)

    # Auto-open X11 app
    run_cmd_stream("am start -n com.termux.x11/com.termux.x11.MainActivity 2>&1")
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

    # Start in background (--isolated: no Termux binaries leak into container)
    cmd = (
        f"proot-distro login arinanolabs --isolated --bind /tmp:/tmp -- su - admin -c '"
        f"{env_str} && "
        f"rm -f /tmp/dbus-* 2>/dev/null && "
        f"dbus-launch --exit-with-session mate-session"
        f"' &"
    )

    run_cmd_stream(cmd)
    time.sleep(3)

    # Verify
    rc, _ = run_cmd("pgrep -f mate-session")
    return rc == 0
