"""installer/isolation.py: proot isolation presets.

    python tests/test_isolation.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run


def test_isolation_presets_are_coherent() -> None:
    """Every preset must be findable by name, and the default must be the
    one with no extra flags — container_command() falls back to it whenever
    nothing has been measured yet, and that fallback must not change what
    every existing session already does."""
    from installer import isolation

    names = [p.name for p in isolation.PRESETS]
    check(len(names) == len(set(names)), f"duplicate preset names: {names}")
    check("default" in names, "the unmodified default is missing")
    check(isolation.DEFAULT_PRESET.flags == "", "the default preset carries extra flags")
    check(isolation.DEFAULT_PRESET is isolation.PRESETS[0], "default is not PRESETS[0]")

    for preset in isolation.PRESETS:
        check(isolation.preset_by_name(preset.name) is preset, f"{preset.name} not findable")

    check(
        isolation.preset_by_name("nonexistent") is None,
        "an unknown preset name resolved to something",
    )


def test_isolation_load_preset_defaults_when_unset() -> None:
    """No prior measurement must mean the unmodified default, not a crash
    or None — every caller of container_command() unconditionally calls
    load_preset()."""
    from installer import config, isolation

    original = config.get(isolation.PROFILE_KEY)
    try:
        config.unset(isolation.PROFILE_KEY)
        check(
            isolation.load_preset() is isolation.DEFAULT_PRESET,
            "an unset profile did not fall back to the default preset",
        )
    finally:
        if original is None:
            config.unset(isolation.PROFILE_KEY)
        else:
            config.set_value(isolation.PROFILE_KEY, original)


def test_isolation_set_preset_manually_clears_score() -> None:
    """A Settings override (set_preset_manually) has no measured score —
    leaving a stale one from an earlier iobench run would misreport the
    override as something iobench actually measured."""
    from installer import config, isolation

    original_profile = config.get(isolation.PROFILE_KEY)
    original_score = config.get(isolation.SCORE_KEY)
    try:
        check(
            isolation.save_preset(isolation.PRESETS[0], 123.0),
            "could not save a measured preset",
        )
        check(config.get(isolation.SCORE_KEY) == "123.0", "score did not round-trip")

        check(
            isolation.set_preset_manually(isolation.PRESETS[1]),
            "manual override reported failure",
        )
        check(isolation.load_preset() is isolation.PRESETS[1], "manual override did not stick")
        check(config.get(isolation.SCORE_KEY) is None, "a stale score survived a manual override")
    finally:
        for key, value in (
            (isolation.PROFILE_KEY, original_profile),
            (isolation.SCORE_KEY, original_score),
        ):
            if value is None:
                config.unset(key)
            else:
                config.set_value(key, value)


TESTS = [
    test_isolation_presets_are_coherent,
    test_isolation_load_preset_defaults_when_unset,
    test_isolation_set_preset_manually_clears_score,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
