"""Audio: the PulseAudio server runs in Termux, clients run in the container.

The container has no sound hardware. It reaches the Termux server over TCP,
which means three things have to be true at once — the server is up, its TCP
module is loaded, and a sink exists on the Android side. Any one of them
missing is silence, and they fail in different places, so the test below
checks the Termux side and the container side separately.

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

# Termux's PulseAudio listens here and the session points clients at it.
PULSE_PORT = 4713
PULSE_SERVER = "tcp:127.0.0.1"

TEST_TONE_NAME = "arinanolabs-test-tone.wav"

PLAY_SCRIPT = f"""#!/bin/bash
export PULSE_SERVER={PULSE_SERVER}
echo "server: $PULSE_SERVER"
pactl info 2>&1 | grep -E "Server (Name|Version)|Default Sink" | sed 's/^/  /'
echo "playing..."
paplay /tmp/{TEST_TONE_NAME} 2>&1
echo "exit: $?"
"""


def server_running() -> bool:
    rc, _ = run_cmd("pgrep -f pulseaudio")
    return rc == 0


def tcp_module_loaded() -> bool:
    rc, out = run_cmd("pactl list modules short 2>/dev/null")
    return rc == 0 and "module-native-protocol-tcp" in out


def sinks() -> list[str]:
    """Output devices PulseAudio knows about. No sink means no sound."""
    rc, out = run_cmd("pactl list sinks short 2>/dev/null")
    if rc != 0:
        return []
    return [line.split("\t")[1] for line in out.splitlines() if "\t" in line]


# Loaded by the daemon itself rather than by a client afterwards. Runtime
# loading needs pactl to connect and authenticate, and when that fails the
# module never loads — the container is then silent with no obvious cause.
# Every published Termux recipe passes it at startup for this reason.
TCP_MODULE_ARGS = "module-native-protocol-tcp auth-ip-acl=127.0.0.1 auth-anonymous=1"


def ensure_server(log: Log) -> bool:
    """Get PulseAudio running with the TCP module loaded.

    Restarts the daemon when the module is missing: --start does not apply
    new --load arguments to a server that is already up, so a daemon started
    without the module can never gain it that way.
    """
    if server_running() and tcp_module_loaded():
        log("  already running with the TCP module")
        return True

    if server_running():
        log("  restarting PulseAudio so the TCP module can be loaded")
        run_cmd("pulseaudio --kill")
        time.sleep(1)

    stream_cmd(
        f'pulseaudio --start --exit-idle-time=-1 --load="{TCP_MODULE_ARGS}"',
        log,
        timeout=60,
    )
    time.sleep(1)

    if tcp_module_loaded():
        return True

    # Fall back to loading it at runtime after all — worth a try before
    # giving up, and it works when the client can authenticate.
    log("  startup load did not take, trying pacmd")
    stream_cmd(f"pacmd load-module {TCP_MODULE_ARGS}", log, timeout=60)
    if tcp_module_loaded():
        return True

    log("  [red]module-native-protocol-tcp is not loaded[/red]")
    log("  the container has no route to the audio server")
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
                frames += struct.pack("<h", int(gain * 32767 * math.sin(2 * math.pi * hz * i / rate)))
            out.writeframes(bytes(frames))
        return True
    except (OSError, wave.Error):
        return False


def test(log: Log) -> None:
    """Play a tone from Termux, then from the container.

    Two stages on purpose. If Termux plays and the container does not, the
    fault is the TCP path or PULSE_SERVER. If neither plays, it is the Android
    side and nothing in the container will help.
    """
    log("── Termux side ───────────────────────────────")

    # Prepared, not merely reported. Stop kills PulseAudio and takes the
    # module with it, so a test run after stopping the desktop would
    # otherwise always report a failure it was itself able to fix.
    log("Preparing the audio server...")
    ensure_server(log)
    log("")
    log(f"server running: {server_running()}")
    log(f"TCP module:     {tcp_module_loaded()}")

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

    log("Playing from inside the container (tests the TCP path)...")
    if not write_container_script("arinanolabs-audio.sh", PLAY_SCRIPT):
        log("[red]Could not write the playback script.[/red]")
        return

    # --shared-tmp puts the tone at /tmp inside, which is where the script
    # looks for it.
    stream_cmd(
        f"proot-distro login {CONTAINER_NAME} --shared-tmp "
        "-- bash /tmp/arinanolabs-audio.sh",
        log,
        timeout=90,
    )

    log("")
    log("[dim]Heard both     -> audio works; check the app's own volume.[/dim]")
    log("[dim]Termux only    -> the container cannot reach the server; check[/dim]")
    log("[dim]                  the TCP module and PULSE_SERVER.[/dim]")
    log("[dim]Heard neither  -> the Android side has no working sink.[/dim]")
    log("")
    log("[dim]Recording is not possible on this stack: the Termux app does[/dim]")
    log("[dim]not declare RECORD_AUDIO, so there is no microphone source.[/dim]")
