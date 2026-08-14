"""Plain-text editor for ~/.claude/CLAUDE.md, Claude Code's global memory
file inside the container.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid
from textual.widgets import Button, Footer, Header, Label, Static, TextArea

from .. import claude_md
from ..system import is_installed
from .common import CopyableScreen


class ClaudeMdScreen(CopyableScreen):
    """Plain-text editor for ~/.claude/CLAUDE.md, Claude Code's global
    memory file inside the container."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self.status_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("CLAUDE.md editor", classes="screen-title")
        yield Static(
            "~/.claude/CLAUDE.md inside the container, loaded at the start "
            "of every Claude Code session.",
            id="claude-md-note",
        )
        yield TextArea(id="claude-md-text")
        yield Static("", id="claude-md-status")
        with Grid(classes="row3"):
            yield Button("Save", id="save", variant="success")
            yield Button("C", id="copy")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def _status(self, message: str) -> None:
        self.status_text = message
        self.query_one("#claude-md-status", Static).update(message)

    def on_mount(self) -> None:
        if not is_installed():
            self._status("No container yet — install it first from the main menu.")
        self.query_one("#claude-md-text", TextArea).text = claude_md.read()

    def on_screen_resume(self) -> None:
        self.query_one("#claude-md-text", TextArea).text = claude_md.read()

    def copy_payload(self) -> str:
        return self.query_one("#claude-md-text", TextArea).text

    @on(Button.Pressed, "#save")
    def _save(self) -> None:
        content = self.query_one("#claude-md-text", TextArea).text
        lines: list[str] = []
        if claude_md.write(content, lines.append):
            self._status("Saved.")
        else:
            self._status("\n".join(lines) or "Could not save.")

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()
