"""Termux packages the container already provides.

Removal is never folded into Doctor's Fix: uninstalling from Termux is the
user's call about their own environment, not a repair.
"""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

from .. import duplicates
from ..system import get_version
from .common import ActionScreen, ConfirmScreen, CopyableScreen, ScrollableTable, when_confirmed


class DupesScreen(CopyableScreen):
    """Termux packages the container already provides.

    Removal is never folded into Doctor's Fix: uninstalling from Termux is
    the user's call about their own environment, not a repair.
    """

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._dupes: list[duplicates.Duplicate] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Termux duplicates", classes="screen-title")
        yield Static(
            "proot-distro binds Termux's $PREFIX into the container and adds "
            "its bin directory to the guest PATH, so these tools exist twice. "
            "The container's copy wins; the Termux one only runs when Debian "
            "lacks the tool.",
            id="dupes-note",
        )
        yield ScrollableTable(id="dupes-table", cursor_type="row", zebra_stripes=True)
        with Grid(classes="row2"):
            yield Button("Re-scan", id="rescan")
            yield Button("Remove", id="remove", variant="error", disabled=True)
        with Horizontal(id="action-buttons"):
            yield Button("C", id="copy")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#dupes-table", DataTable).add_columns(
            "Termux package", "Container provides"
        )
        self.query_one("#copy", Button).tooltip = "Copy this list"
        self.query_one("#remove", Button).tooltip = "Uninstall these from Termux only"

    def on_screen_resume(self) -> None:
        self.scan()

    @work(thread=True)
    def scan(self) -> None:
        self.app.call_from_thread(self._show, duplicates.termux_duplicates())

    def _show(self, dupes: list[duplicates.Duplicate]) -> None:
        self._dupes = dupes
        table = self.query_one("#dupes-table", DataTable)
        table.clear()
        for dupe in dupes:
            table.add_row(dupe.package, dupe.binary)

        button = self.query_one("#remove", Button)
        button.disabled = not dupes
        button.label = f"Remove ({len(dupes)})" if dupes else "Remove"

    def copy_payload(self) -> str:
        lines = [f"XLabs Termux duplicates — {get_version()}", ""]
        if not self._dupes:
            lines.append("(none)")
        lines += [f"{d.package:<14} -> container has {d.binary}" for d in self._dupes]
        return "\n".join(lines)

    @on(Button.Pressed, "#rescan")
    def _rescan(self) -> None:
        self.scan()

    @on(Button.Pressed, "#remove")
    def _remove(self) -> None:
        packages = [d.package for d in self._dupes]
        if not packages:
            return

        def run(log) -> None:
            if duplicates.remove_termux_packages(packages, log):
                log("")
                log("[green]Removed.[/green] The container's copies are unaffected.")
            else:
                log("")
                log("[red]Removal failed or was refused.[/red]")

        self.app.push_screen(
            ConfirmScreen(
                "Remove from Termux",
                "Uninstall these from Termux, keeping the container's copies:\n\n"
                + ", ".join(packages)
                + "\n\nThe container is unaffected. Anything you run directly in "
                "Termux that needs these will stop working.",
                confirm_label="Uninstall",
            ),
            when_confirmed(self.app, lambda: ActionScreen("Remove duplicates", run)),
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()
