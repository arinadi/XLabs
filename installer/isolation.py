"""Which proot-distro login flags this device's sessions run under.

--shared-tmp is not one of these presets — write_container_script() and
container_command() depend on it structurally (the script placed in Termux's
tmp has to be visible inside the container), so every session carries it
regardless of this setting. What these presets vary is Android/host binding:
`--isolated` skips mounting /sdcard and the Termux $HOME, which means fewer
bind-mount entries for proot's ptrace layer to resolve on every open/stat/
read. Whether that is actually faster depends on the device and the bind
count it would otherwise carry, so it is measured (iobench.py) rather than
assumed — the same reasoning bench.py already uses for the GPU presets.
"""

from __future__ import annotations

import os
from typing import NamedTuple

from . import config

PROFILE_KEY = "PROOT_ISOLATION"
SCORE_KEY = "PROOT_ISOLATION_SCORE"

# termux-setup-storage's symlink target — the usual way in to phone storage
# once --isolated has stopped binding it automatically.
STORAGE_BIND = os.path.expanduser("~/storage/shared")


class Preset(NamedTuple):
    name: str
    description: str
    # Extra proot-distro login flags beyond --shared-tmp.
    flags: str


PRESETS = (
    Preset("default", "Full Android/host access (default)", ""),
    Preset("isolated", "Isolated — skip Android bindings", "--isolated"),
    Preset(
        "isolated-storage",
        "Isolated + /mnt/android storage",
        f"--isolated --bind {STORAGE_BIND}:/mnt/android",
    ),
)

DEFAULT_PRESET = PRESETS[0]


def preset_by_name(name: str) -> Preset | None:
    return next((p for p in PRESETS if p.name == name), None)


def load_preset() -> Preset:
    """The configuration a previous iobench chose, or the safe default."""
    name = config.get(PROFILE_KEY)
    return (preset_by_name(name) if name else None) or DEFAULT_PRESET


def save_preset(preset: Preset, score: float) -> bool:
    return config.set_value(PROFILE_KEY, preset.name) and config.set_value(
        SCORE_KEY, str(score)
    )


def set_preset_manually(preset: Preset) -> bool:
    """A Settings override rather than a measured result — clears the score
    rather than leaving a stale one from whatever preset was measured
    before, which would misreport this pick as benchmarked."""
    return config.set_value(PROFILE_KEY, preset.name) and config.unset(SCORE_KEY)
