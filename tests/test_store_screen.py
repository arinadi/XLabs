"""StoreScreen, ReposScreen, AddRepoScreen, MirrorScreen.

    python tests/test_store_screen.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run
from textual.widgets import Button, DataTable, Input

from installer import packages
from installer.app import (
    AddRepoScreen,
    ConfirmScreen,
    MirrorScreen,
    ReposScreen,
    StoreScreen,
    XLabsApp,
)


async def test_store_screen_searches() -> None:
    from installer.app import MainScreen

    app = XLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#store")
        await pilot.pause()
        check(isinstance(app.screen, StoreScreen), f"got {app.screen!r}")

        check(
            app.screen.query_one("#install", Button).disabled,
            "Install was offered before any search",
        )

        # No container off-device, so this exercises the error path.
        app.screen.query_one("#query", Input).value = "neovim"
        await pilot.press("enter")
        for _ in range(40):
            await asyncio.sleep(0.1)
            await pilot.pause()
            if "Searching" not in app.screen.status_text:
                break
        check(app.screen.status_text, "the search reported nothing at all")
        check(
            "Searching" not in app.screen.status_text,
            f"the search never finished: {app.screen.status_text!r}",
        )
        check(
            app.screen.query_one("#install", Button).disabled,
            "Install was enabled with no results",
        )

        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


async def test_multi_select_checkboxes() -> None:
    """Space checks the highlighted row into the Install batch if it's not
    installed, or the Uninstall batch if it is. Either button then acts on
    its batch, or falls back to the highlighted row alone if nothing is
    checked for it."""
    app = XLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#store")
        await pilot.pause()
        store = app.screen
        check(isinstance(store, StoreScreen), f"got {store!r}")

        # No container off-device, so results are seeded directly rather
        # than through a real search/curated load.
        fake = [
            packages.Package("alpha", "first tool", False),
            packages.Package("beta", "second tool", False),
            packages.Package("gamma", "already there", True),
        ]
        store._show(fake, None, kind="search")
        await pilot.pause()

        table = store.query_one("#store-table", DataTable)
        table.focus()

        table.move_cursor(row=0)
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        check(store._to_install == {"alpha"}, f"space did not check the row: {store._to_install}")
        install = store.query_one("#install", Button)
        check(
            str(install.label) == "Install (1)",
            f"install label did not reflect the checked count: {install.label!r}",
        )

        table.move_cursor(row=1)
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        check(
            store._to_install == {"alpha", "beta"},
            f"second check lost the first: {store._to_install}",
        )

        # An already-installed row joins the Uninstall batch instead.
        table.move_cursor(row=2)
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        check(store._to_uninstall == {"gamma"}, f"installed row did not check: {store._to_uninstall}")
        uninstall = store.query_one("#uninstall", Button)
        check(
            str(uninstall.label) == "Uninstall (1)",
            f"uninstall label did not reflect the checked count: {uninstall.label!r}",
        )

        # Toggling an already-checked row off works too.
        table.move_cursor(row=0)
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        check(store._to_install == {"beta"}, f"toggling off did not remove it: {store._to_install}")

        await pilot.click("#install")
        await pilot.pause()
        check(isinstance(app.screen, ConfirmScreen), f"got {app.screen!r}")
        check(store._to_install == set(), "Install did not clear its batch for the pending run")
        check(store._to_uninstall == {"gamma"}, "Install disturbed the separate Uninstall batch")

        await pilot.click("#cancel")
        await pilot.pause()
        check(isinstance(app.screen, StoreScreen), "cancel did not return to Store")

        await pilot.click("#uninstall")
        await pilot.pause()
        check(isinstance(app.screen, ConfirmScreen), f"got {app.screen!r}")
        title = str(app.screen.query_one("#dialog-title").content)
        check("Uninstall gamma" in title, f"the batch did not target gamma: {title!r}")
        check(store._to_uninstall == set(), "Uninstall did not clear its batch for the pending run")

        await pilot.click("#cancel")
        await pilot.pause()

        # Nothing checked: Install falls back to the highlighted row alone.
        table.move_cursor(row=0)
        await pilot.pause()
        await pilot.click("#install")
        await pilot.pause()
        check(isinstance(app.screen, ConfirmScreen), "the single-row fallback did not confirm")
        title = str(app.screen.query_one("#dialog-title").content)
        check("Install alpha" in title, f"the fallback did not target the highlighted row: {title!r}")

        await pilot.click("#cancel")
        await pilot.pause()

        # Nothing checked: Uninstall falls back to the highlighted row,
        # refusing one that isn't actually installed.
        table.move_cursor(row=0)
        await pilot.pause()
        await pilot.click("#uninstall")
        await pilot.pause()
        check(
            isinstance(app.screen, StoreScreen),
            "Uninstall confirmed against a not-installed highlighted row",
        )
        check("not installed" in store.status_text, f"no refusal shown: {store.status_text!r}")

        await pilot.click("#back")
        await pilot.pause()


async def test_row_selection_shows_before_confirm() -> None:
    """A DataTable row is a thin touch target — one line tall, no gutter
    between rows — so a mistap is easy on a phone screen. Repos and Mirror
    both have real data without a container, so highlighting a row there
    must update the status line before any button is pressed, not only
    inside the confirm dialog that follows it."""
    app = XLabsApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#store")
        await pilot.pause()

        await pilot.click("#repos")
        await pilot.pause()
        check(isinstance(app.screen, ReposScreen), f"got {app.screen!r}")
        # DataTable highlights row 0 by default the moment rows exist, so
        # the note already names a pick before any tap of its own.
        check(
            app.screen.status_text.startswith("Selected:"),
            f"the default row highlight did not update the note: {app.screen.status_text!r}",
        )
        table = app.screen.query_one("#repos-table", DataTable)
        if table.row_count > 1:
            table.move_cursor(row=1)
            await pilot.pause()
            check(
                app.screen.status_text.startswith("Selected:"),
                f"highlighting a different repo row lost the note: {app.screen.status_text!r}",
            )
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, StoreScreen), "back from Repos did not return")

        await pilot.click("#mirror")
        await pilot.pause()
        check(isinstance(app.screen, MirrorScreen), f"got {app.screen!r}")
        # DataTable highlights row 0 by default the moment rows exist, so
        # the status line already names a pick before any tap of its own.
        check(
            app.screen.status_text.startswith("Selected:"),
            f"the default row highlight did not update the status: {app.screen.status_text!r}",
        )
        # The regular refresh must still restore it afterward — this is a
        # shared line, not a dedicated one, so nothing may be lost for good.
        app.screen._refresh_current()
        check(
            not app.screen.status_text.startswith("Selected:"),
            "the highlight text survived a refresh instead of being replaced",
        )


async def test_add_repo_screen() -> None:
    """The custom-repo form: validation blocks bad input, a good one reaches
    confirmation, and every control stays reachable at phone widths.

    Two clicks on the same button in quick succession is a known pacing
    issue in Textual's test pilot rather than anything about this screen —
    calling the handler directly showed the logic was correct before the
    delay was added, so this is not papering over a real bug.
    """
    for width, height in ((80, 40), (45, 30), (40, 24)):
        app = XLabsApp()
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            await pilot.click("#store")
            await pilot.pause()
            await pilot.click("#repos")
            await pilot.pause()
            check(isinstance(app.screen, ReposScreen), f"got {app.screen!r}")
            for button in app.screen.query(Button):
                check(
                    app.screen.region.contains_region(button.region),
                    f"{button.id} off screen at {width}x{height} on ReposScreen",
                )

            await pilot.click("#add")
            await pilot.pause()
            check(isinstance(app.screen, AddRepoScreen), f"got {app.screen!r}")
            for button in app.screen.query(Button):
                check(
                    app.screen.region.contains_region(button.region),
                    f"{button.id} off screen at {width}x{height} on AddRepoScreen",
                )

            await pilot.click("#submit")
            await asyncio.sleep(0.15)
            await pilot.pause()
            check(isinstance(app.screen, AddRepoScreen), "empty submit left the form")
            check("Name:" in app.screen.status_text, f"no validation message: {app.screen.status_text!r}")

            app.screen.query_one("#repo-name", Input).value = "syncthing"
            app.screen.query_one("#repo-uri", Input).value = "https://apt.syncthing.net/"
            app.screen.query_one("#repo-suites", Input).value = "syncthing"
            app.screen.query_one("#repo-key", Input).value = "https://syncthing.net/release-key.gpg"
            await asyncio.sleep(0.15)
            await pilot.pause()

            await pilot.click("#submit")
            await asyncio.sleep(0.15)
            await pilot.pause()
            check(
                isinstance(app.screen, ConfirmScreen),
                f"valid submit did not reach confirmation at {width}x{height}: {app.screen!r}",
            )

            await pilot.click("#cancel")
            await pilot.pause()
            check(isinstance(app.screen, AddRepoScreen), "cancel discarded the form")

            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, ReposScreen), "back from the form did not return")
            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, StoreScreen), "back from Repos did not return")


TESTS = [
    test_store_screen_searches,
    test_multi_select_checkboxes,
    test_row_selection_shows_before_confirm,
    test_add_repo_screen,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
