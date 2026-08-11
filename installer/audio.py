"""Audio: the PulseAudio server runs in Termux, clients run in the container.

The container has no sound hardware, and it does not need networking to reach
the server either. --shared-tmp binds Termux's tmp over the container's /tmp,
so a Unix socket in $PREFIX/tmp is simply a file the container can open.

TCP was the documented approach everywhere and it failed on a real device:
the module loaded, `pactl list modules` listed it, and every address the
container tried was refused — listed but not listening. The socket removes
the question entirely: no port, no binding, no loopback.

Recording is not supported and cannot be: the Termux app does not declare
android.permission.RECORD_AUDIO, module-sles-source fails to initialise, and
forcing it yields silence rather than audio.
"""

from __future__ import annotations

import math
import os
import struct
import time
import wave
from typing import Callable

from .const import CONTAINER_NAME, TMPDIR
from .system import is_installed, run_cmd, stream_cmd, write_container_script

Log = Callable[[str], None]

# On the Termux side. This project's uninstall script has always cleaned up
# $TMPDIR/pulse-socket, which suggests the original setup used it too.
PULSE_SOCKET = f"{TMPDIR}/pulse-socket"

# What clients inside the container use: with --shared-tmp, /tmp there is
# Termux's tmp here.
PULSE_SERVER = "unix:/tmp/pulse-socket"

MODULE_ARGS = f"module-native-protocol-unix socket={PULSE_SOCKET} auth-anonymous=1"

TEST_TONE_NAME = "arinanolabs-test-tone.wav"

PLAY_SCRIPT = f"""#!/bin/bash
# Connecting and playing are different failures, and a bare exit code cannot
# tell them apart. This reports each separately.

echo "paplay: $(command -v paplay || echo MISSING)"
echo "socket: $(ls -l /tmp/pulse-socket 2>&1)"
echo "tone:   $(ls -l /tmp/{TEST_TONE_NAME} 2>&1)"
echo

export PULSE_SERVER={PULSE_SERVER}
echo "PULSE_SERVER=$PULSE_SERVER"
if ! pactl info >/dev/null 2>&1; then
    echo "could not reach the server:"
    pactl info 2>&1 | sed 's/^/    /'
    exit 1
fi

pactl info 2>&1 | grep -E "Server String|Server Name|Default Sink" | sed 's/^/    /'
echo
echo "sinks visible from in here:"
pactl list sinks short 2>&1 | sed 's/^/    /'
echo
echo "volume and mute:"
pactl list sinks 2>&1 | grep -E "^[[:space:]]+(Volume|Mute)" | head -4 | sed 's/^/    /'
echo
echo "playing..."
paplay --verbose /tmp/{TEST_TONE_NAME} 2>&1 | sed 's/^/    /'
echo "exit: ${{PIPESTATUS[0]}}"
"""


def server_running() -> bool:
    rc, _ = run_cmd("pgrep -f pulseaudio")
    return rc == 0


def socket_ready() -> bool:
    """The socket exists and the server answers on it.

    Checked by connecting, not by listing modules. A module can be loaded and
    still accept nothing — which is exactly how the TCP path failed while
    every check reported success.
    """
    if not os.path.exists(PULSE_SOCKET):
        return False
    rc, _ = run_cmd(f"pactl -s unix:{PULSE_SOCKET} info")
    return rc == 0


def sinks() -> list[str]:
    """Output devices PulseAudio knows about. No sink means no sound."""
    rc, out = run_cmd("pactl list sinks short 2>/dev/null")
    if rc != 0:
        return []
    return [line.split("\t")[1] for line in out.splitlines() if "\t" in line]


def ensure_server(log: Log) -> bool:
    """Get PulseAudio running with a socket the container can open.

    Success means a connection was made, not that a module appeared in a
    list. Restarts the daemon when the socket is missing: --start does not
    apply new --load arguments to a server that is already up.
    """
    if server_running() and socket_ready():
        log("  already running, socket ready")
        return True

    if server_running():
        log("  restarting PulseAudio to open the socket")
        run_cmd("pulseaudio --kill")
        time.sleep(1)

    run_cmd(f"rm -f {PULSE_SOCKET}")
    stream_cmd(
        f'pulseaudio --start --exit-idle-time=-1 --load="{MODULE_ARGS}"',
        log,
        timeout=60,
    )
    time.sleep(1)

    if socket_ready():
        log(f"  socket ready at {PULSE_SOCKET}")
        return True

    # Loading at startup is preferred because it needs no client connection,
    # but trying at runtime costs nothing before giving up.
    log("  socket did not open, loading the module at runtime")
    stream_cmd(f"pacmd load-module {MODULE_ARGS}", log, timeout=60)
    if socket_ready():
        log(f"  socket ready at {PULSE_SOCKET}")
        return True

    log("  [red]the socket is not accepting connections[/red]")
    return False


def write_test_tone(path: str, seconds: float = 1.0, hz: int = 440) -> bool:
    """Write a short sine wave. Generated rather than shipped: the vanilla
    image has no sound files and this avoids adding a package for one beep."""
    rate = 16000
    try:
        with wave.open(path, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            frames = bytearray()
            for i in range(int(rate * seconds)):
                # Fade the last 10% so it ends without a click.
                progress = i / (rate * seconds)
                gain = 0.3 * (1.0 if progress < 0.9 else (1.0 - progress) * 10)
                sample = gain * 32767 * math.sin(2 * math.pi * hz * i / rate)
                frames += struct.pack("<h", int(sample))
            out.writeframes(bytes(frames))
        return True
    except (OSError, wave.Error):
        return False


def test(log: Log) -> None:
    """Play a tone from Termux, then from the container.

    Two stages on purpose. If Termux plays and the container does not, the
    fault is between them. If neither plays, it is the Android side and
    nothing in the container will help.
    """
    log("── Termux side ───────────────────────────────")

    # Prepared, not merely reported. Stop kills PulseAudio and takes the
    # socket with it, so a test run after stopping the desktop would
    # otherwise always report a failure it was itself able to fix.
    log("Preparing the audio server...")
    ensure_server(log)
    log("")
    log(f"server running: {server_running()}")
    log(f"socket answers: {socket_ready()}  ({PULSE_SOCKET})")

    found = sinks()
    log(f"sinks:          {', '.join(found) if found else 'NONE — nothing can play'}")
    log("")

    tone = os.path.join(TMPDIR, TEST_TONE_NAME)
    if not write_test_tone(tone):
        log("[red]Could not write the test tone.[/red]")
        return
    log(f"test tone: {tone}")
    log("")

    log("Playing from Termux (tests the Android audio path)...")
    rc = stream_cmd(f"paplay {tone}", log, timeout=30)
    log(f"  exit {rc}" + ("" if rc == 0 else "  [yellow]no sound from Termux itself[/yellow]"))
    log("")

    if not is_installed():
        log("No container, so the second half is skipped.")
        return

    log("Playing from inside the container (tests the shared socket)...")
    if not write_container_script("arinanolabs-audio.sh", PLAY_SCRIPT):
        log("[red]Could not write the playback script.[/red]")
        return

    stream_cmd(
        f"proot-distro login {CONTAINER_NAME} --shared-tmp "
        "-- bash /tmp/arinanolabs-audio.sh",
        log,
        timeout=90,
    )

    log("")
    log("[dim]Reading the container half:[/dim]")
    log("[dim]  could not reach the server -> see whether the socket file[/dim]")
    log("[dim]     exists above; --shared-tmp is what makes it visible.[/dim]")
    log("[dim]  reached it, exit 0, silent -> the path works and the sound is[/dim]")
    log("[dim]     going elsewhere. Check the volume and mute lines.[/dim]")
    log("[dim]  reached it, non-zero exit  -> the error above says why.[/dim]")
    log("")
    log("[dim]Recording is not possible on this stack: the Termux app does[/dim]")
    log("[dim]not declare RECORD_AUDIO, so there is no microphone source.[/dim]")
