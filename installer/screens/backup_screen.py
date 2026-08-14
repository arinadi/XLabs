"""Back up and restore the container's home directory.

This is the user's own files and settings — not apt packages, which a plain
Reset already reinstalls on its own.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

from .. import backup
from ..system import is_installed
from .common import ActionScreen, ConfirmScreen, ScrollableTable, when_confirmed


class BackupScreen(Screen):
    """Back up and restore the container's home directory.

    This is the user's own files and settings — not apt packages, which a
    plain Reset already reinstalls on its own.
    """

    BINDINGS = [("escape", "back", "Back")]

    NOTE = (
        f"Archives {backup.HOME_IN_CONTAINER} — files, the Firefox profile, "
        "editor settings, the panel layout. Not apt packages; those come "
        "back with a normal install."
    )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Backup", classes="screen-title")
        yield Static(self.NOTE, id="backup-note")
        yield ScrollableTable(id="backup-table", cursor_type="row", zebra_stripes=True)
        with Grid(classes="row3"):
            yield Button("Backup now", id="create", variant="success")
            yield Button("Restore", id="restore")
            yield Button("Delete", id="delete", variant="error")
        yield Button("Back", id="back", variant="primary")
        yield Footer()

    def __init__(self) -> None:
        super().__init__()
        self._backups: list[backup.Backup] = []
        # Kept alongside the widget: Static does not expose its text back.
        self.status_text = self.NOTE

    def _note(self, message: str) -> None:
        self.status_text = message
        self.query_one("#backup-note", Static).update(message)

    def on_mount(self) -> None:
        self.query_one("#backup-table", DataTable).add_columns("Name", "Size", "Created")
        self._fill()

    def on_screen_resume(self) -> None:
        self._fill()

    def _fill(self) -> None:
        self._backups = backup.list_backups()
        table = self.query_one("#backup-table", DataTable)
        table.clear()
        for b in self._backups:
            table.add_row(b.name, backup.human_size(b.size_bytes), b.created.strftime("%Y-%m-%d %H:%M"))
        # The list just changed shape, so any earlier highlight no longer
        # points at what it used to.
        self._note(self.NOTE)

    def _selected(self) -> backup.Backup | None:
        row = self.query_one("#backup-table", DataTable).cursor_row
        if row is None or not (0 <= row < len(self._backups)):
            return None
        return self._backups[row]

    @on(DataTable.RowHighlighted, "#backup-table")
    def _row_highlighted(self) -> None:
        # Reuses the note line rather than adding a row for this: on a
        # phone-height screen there is no free row to spare, and a table
        # row is thin enough to mistap, so naming the pick here — not only
        # inside the confirm dialog — catches that before Restore/Delete is
        # even pressed. Restore is the one that can undo real work if it
        # lands on the wrong archive.
        b = self._selected()
        if b is not None:
            self._note(f"Selected: {b.name} ({backup.human_size(b.size_bytes)})")

    @on(Button.Pressed, "#create")
    def _create(self) -> None:
        if not is_installed():
            self.notify("No container to back up.", severity="warning")
            return

        def run(log) -> None:
            backup.create_backup(log)

        self.app.push_screen(
            ConfirmScreen(
                "Back up home",
                f"Archives {backup.HOME_IN_CONTAINER} to {backup.BACKUP_DIR} on "
                "Termux's own storage.\n\n"
                "Can take a while for a large Firefox cache or node_modules.",
                confirm_label="Back up",
            ),
            when_confirmed(self.app, lambda: ActionScreen("Backup", run)),
        )

    @on(Button.Pressed, "#restore")
    def _restore(self) -> None:
        b = self._selected()
        if b is None:
            self.notify("Highlight a backup first.", severity="warning")
            return

        def run(log) -> None:
            backup.restore_backup(b, log)

        self.app.push_screen(
            ConfirmScreen(
                f"Restore {b.name}",
                f"Replaces {backup.HOME_IN_CONTAINER} with this backup's contents.\n\n"
                "The current home is kept as a .bak inside the container "
                "rather than deleted, in case this turns out to be the wrong "
                "pick.",
                confirm_label="Restore",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Restore {b.name}", run)),
        )

    @on(Button.Pressed, "#delete")
    def _delete(self) -> None:
        b = self._selected()
        if b is None:
            self.notify("Highlight a backup first.", severity="warning")
            return

        def run(log) -> None:
            backup.delete_backup(b, log)

        self.app.push_screen(
            ConfirmScreen(
                f"Delete {b.name}",
                "This only removes the saved archive — it does not touch the "
                "container.",
                confirm_label="Delete",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Delete {b.name}", run)),
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()
