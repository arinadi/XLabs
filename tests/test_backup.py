"""installer/backup.py and installer/presets.py: Backup screen, Reset's
preset-restore checkbox.

    python tests/test_backup.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run
from textual.widgets import Checkbox

from installer import app as app_module
from installer import backup, presets
from installer.app import BackupScreen, ConfirmScreen, MainScreen, XLabsApp


def test_backup_list_and_human_size() -> None:
    """list_backups() must only see its own archives, newest first, and
    survive a BACKUP_DIR that does not exist yet."""
    check(backup.list_backups() == [], "a missing BACKUP_DIR must read as no backups, not an error")

    for byte_count, expected in ((0, "0B"), (999, "999B"), (2048, "2.0KB"), (5 * 1024**3, "5.0GB")):
        check(
            backup.human_size(byte_count) == expected,
            f"human_size({byte_count}) = {backup.human_size(byte_count)!r}, expected {expected!r}",
        )

    fake_dir = tempfile.mkdtemp()
    original_dir = backup.BACKUP_DIR
    backup.BACKUP_DIR = fake_dir
    try:
        for name, age in (("home-20240101-000000.tar.gz", 200), ("home-20240102-000000.tar.gz", 100)):
            path = os.path.join(fake_dir, name)
            with open(path, "wb") as f:
                f.write(b"0" * 1024)
            then = time.time() - age
            os.utime(path, (then, then))
        # Not a backup this tool made — must not show up or be touchable.
        with open(os.path.join(fake_dir, "notes.txt"), "w") as f:
            f.write("hello")

        found = backup.list_backups()
        check(len(found) == 2, f"expected 2 backups, got {len(found)}: {found}")
        check(found[0].name == "home-20240102-000000.tar.gz", "not sorted newest first")
        check(all(b.name.endswith(".tar.gz") for b in found), "a non-archive file was listed")
        check(found[0].size_bytes == 1024, "size was not read from the file")
    finally:
        backup.BACKUP_DIR = original_dir


def test_find_preset_picks_newest() -> None:
    """The newest .tar.gz in presets/ wins; a missing or empty dir reads as
    no preset, not an error, since most installs never add one."""
    original_dir = presets.PRESETS_DIR
    try:
        presets.PRESETS_DIR = os.path.join(tempfile.mkdtemp(), "does-not-exist")
        check(presets.find_preset() is None, "a missing presets/ dir must read as no preset")

        fake_dir = tempfile.mkdtemp()
        presets.PRESETS_DIR = fake_dir
        check(presets.find_preset() is None, "an empty presets/ dir must read as no preset")

        for name, age in (("old.tar.gz", 200), ("new.tar.gz", 50)):
            path = os.path.join(fake_dir, name)
            with open(path, "wb") as f:
                f.write(b"0" * 512)
            then = time.time() - age
            os.utime(path, (then, then))
        with open(os.path.join(fake_dir, "notes.txt"), "w") as f:
            f.write("not a preset")

        found = presets.find_preset()
        check(found is not None, "a populated presets/ dir returned None")
        check(found.name == "new.tar.gz", f"expected the newest archive, got {found.name}")
    finally:
        presets.PRESETS_DIR = original_dir


def test_reset_restores_preset_only_when_requested() -> None:
    """run_reset's restore_preset flag must gate presets.restore_preset —
    Start's first install always passes True, Reset passes the checkbox
    state, and a failed pull must not attempt a restore either way."""
    calls: list[bool] = []

    original_stop = app_module.desktop.stop_desktop
    original_stream = app_module.stream_cmd
    original_pull = app_module.pull_image
    original_mirror = app_module.packages.reapply_saved_mirror
    original_restore = app_module.presets.restore_preset

    app_module.desktop.stop_desktop = lambda log: None
    app_module.stream_cmd = lambda *a, **k: 0
    app_module.packages.reapply_saved_mirror = lambda log: True
    app_module.presets.restore_preset = lambda log: (calls.append(True), True)[1]

    try:
        app_module.pull_image = lambda log: True
        app_module.run_reset(lambda m: None, restore_preset=False)
        check(calls == [], "restore_preset=False must not restore anything")

        app_module.run_reset(lambda m: None, restore_preset=True)
        check(calls == [True], "restore_preset=True must call presets.restore_preset")

        calls.clear()
        app_module.pull_image = lambda log: False
        app_module.run_reset(lambda m: None, restore_preset=True)
        check(calls == [], "a failed pull must not attempt a restore")
    finally:
        app_module.desktop.stop_desktop = original_stop
        app_module.stream_cmd = original_stream
        app_module.pull_image = original_pull
        app_module.packages.reapply_saved_mirror = original_mirror
        app_module.presets.restore_preset = original_restore


async def test_reset_checkbox_reflects_preset_presence() -> None:
    """The Reset confirm dialog only offers the restore checkbox when a
    preset actually exists — nothing to opt into otherwise."""
    original_dir = presets.PRESETS_DIR
    try:
        presets.PRESETS_DIR = os.path.join(tempfile.mkdtemp(), "does-not-exist")
        app = XLabsApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#reset")
            await pilot.pause()
            check(
                not app.screen.query("#dialog-checkbox"),
                "a checkbox appeared with no preset to restore",
            )
            await pilot.click("#cancel")
            await pilot.pause()

        presets.PRESETS_DIR = tempfile.mkdtemp()
        with open(os.path.join(presets.PRESETS_DIR, "home-preset.tar.gz"), "wb") as f:
            f.write(b"0" * 512)

        app = XLabsApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#reset")
            await pilot.pause()
            checkbox = app.screen.query_one("#dialog-checkbox", Checkbox)
            check(checkbox.value is True, "the restore checkbox should default to checked")
            await pilot.click("#cancel")
            await pilot.pause()
    finally:
        presets.PRESETS_DIR = original_dir


async def test_backup_screen() -> None:
    """Backup/Restore/Delete all need a highlighted row; without one they
    must warn rather than crash or silently do nothing. Restore is the one
    that can undo real work if it lands on the wrong archive, so — like
    Repos and Mirror — the pick is named on the note line as soon as a row
    is highlighted, not only inside the confirm dialog that follows it."""
    fake_dir = tempfile.mkdtemp()
    original_dir = backup.BACKUP_DIR
    backup.BACKUP_DIR = fake_dir
    try:
        app = XLabsApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#backup")
            await pilot.pause()
            check(isinstance(app.screen, BackupScreen), f"got {app.screen!r}")

            # No backups yet: Restore/Delete must warn, not crash or guess.
            for button in ("#restore", "#delete"):
                await pilot.click(button)
                await pilot.pause()
                check(
                    isinstance(app.screen, BackupScreen),
                    f"{button} with nothing to select left the screen",
                )

            path = os.path.join(fake_dir, "home-20240101-000000.tar.gz")
            with open(path, "wb") as f:
                f.write(b"0" * 2048)
            app.screen._fill()
            await pilot.pause()

            # DataTable highlights row 0 by default the moment rows exist.
            check(
                app.screen.status_text.startswith("Selected:"),
                f"the default row highlight did not update the note: {app.screen.status_text!r}",
            )
            check(
                "home-20240101-000000.tar.gz" in app.screen.status_text,
                f"the note did not name the highlighted archive: {app.screen.status_text!r}",
            )

            await pilot.click("#restore")
            await pilot.pause()
            check(isinstance(app.screen, ConfirmScreen), "Restore with a row selected did not confirm")
            await pilot.click("#cancel")
            await pilot.pause()

            await pilot.click("#back")
            await pilot.pause()
            check(isinstance(app.screen, MainScreen), "back from Backup did not return")
    finally:
        backup.BACKUP_DIR = original_dir


TESTS = [
    test_backup_list_and_human_size,
    test_find_preset_picks_newest,
    test_reset_restores_preset_only_when_requested,
    test_reset_checkbox_reflects_preset_presence,
    test_backup_screen,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
