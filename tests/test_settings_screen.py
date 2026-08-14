"""SettingsScreen: edits saved through their owning module, not duplicated.

    python tests/test_settings_screen.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run
from textual.widgets import Select

from installer.app import MainScreen, SettingsScreen, XLabsApp


async def test_settings_screen() -> None:
    """Settings edits must be saved through each owning module (audio.py,
    bench.py, start.py) rather than duplicating their logic, and opening
    the screen must not itself count as an edit — Select.value is set
    programmatically on every visit to show the current pick, which would
    otherwise read back as a user changing it."""
    from installer import audio, bench, config, isolation, start

    keys = (
        audio.METHOD_KEY,
        bench.PROFILE_KEY,
        bench.SCORE_KEY,
        start.DRAW_PATH_KEY,
        isolation.PROFILE_KEY,
        isolation.SCORE_KEY,
    )
    original = {k: config.get(k) for k in keys}

    app = XLabsApp()
    try:
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#settings")
            await pilot.pause()
            check(isinstance(app.screen, SettingsScreen), f"got {app.screen!r}")

            check(
                config.get(audio.METHOD_KEY) == original[audio.METHOD_KEY],
                "opening Settings wrote the audio method",
            )
            check(
                config.get(start.DRAW_PATH_KEY) == original[start.DRAW_PATH_KEY],
                "opening Settings wrote the draw path",
            )
            check(
                config.get(isolation.PROFILE_KEY) == original[isolation.PROFILE_KEY],
                "opening Settings wrote the isolation preset",
            )
            check(app.screen.status_text == "", "a status message appeared before any edit")

            select = app.screen.query_one("#settings-x11", Select)
            check(
                select.value == start.load_draw_path(),
                "the X11 select did not show the currently saved value",
            )

            select.value = "force-bgra"
            await pilot.pause()
            check(start.load_draw_path() == "force-bgra", "changing the select did not save")
            check(
                "saved" in app.screen.status_text.lower(),
                f"no confirmation shown after an edit: {app.screen.status_text!r}",
            )

            iso_select = app.screen.query_one("#settings-isolation", Select)
            check(
                iso_select.value == isolation.load_preset().name,
                "the isolation select did not show the currently saved value",
            )
            iso_select.value = "isolated"
            await pilot.pause()
            check(
                isolation.load_preset().name == "isolated",
                "changing the isolation select did not save",
            )
            check(
                config.get(isolation.SCORE_KEY) is None,
                "a manual isolation change through Settings must not carry a measured score",
            )

            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, MainScreen), "back from Settings did not return")
    finally:
        for key, value in original.items():
            if value is None:
                config.unset(key)
            else:
                config.set_value(key, value)


TESTS = [
    test_settings_screen,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
