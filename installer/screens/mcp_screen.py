"""MCP servers in the container's ~/.claude.json.

Unlike Providers, every entry here loads in every Claude Code session
automatically — there is no separate activate step.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TextArea,
)

from .. import mcp_manager
from ..system import is_installed
from .common import ActionScreen, ConfirmScreen, ScrollableTable, when_confirmed


class MCPScreen(Screen):
    """MCP servers in the container's ~/.claude.json.

    Unlike Providers, every entry here loads in every Claude Code session
    automatically — there is no separate activate step.
    """

    BINDINGS = [("escape", "back", "Back")]

    NOTE = (
        "Loaded automatically by Claude Code in every project inside the "
        "container. A server you add can run arbitrary commands or reach "
        "arbitrary URLs on its own account's behalf."
    )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("MCP servers", classes="screen-title")
        yield Static(self.NOTE, id="mcp-note")
        yield ScrollableTable(id="mcp-table", cursor_type="row", zebra_stripes=True)
        with Grid(classes="row2"):
            yield Button("Add", id="add", variant="success")
            yield Button("Remove", id="remove", variant="error")
        yield Button("Back", id="back", variant="primary")
        yield Footer()

    def __init__(self) -> None:
        super().__init__()
        self._servers: list[mcp_manager.MCPServer] = []
        self.status_text = self.NOTE

    def _note(self, message: str) -> None:
        self.status_text = message
        self.query_one("#mcp-note", Static).update(message)

    def on_mount(self) -> None:
        self.query_one("#mcp-table", DataTable).add_columns("Name", "Type", "Command / URL")
        if not is_installed():
            self._note("No container yet — install it first from the main menu.")
        self._fill()

    def on_screen_resume(self) -> None:
        self._fill()

    @staticmethod
    def _detail(server: mcp_manager.MCPServer) -> str:
        if server.type == mcp_manager.STDIO:
            return " ".join([server.command, *server.args]).strip()
        return server.url

    def _fill(self) -> None:
        self._servers = mcp_manager.list_servers()
        table = self.query_one("#mcp-table", DataTable)
        table.clear()
        for s in self._servers:
            table.add_row(s.name, s.type, self._detail(s))

    def _selected(self) -> mcp_manager.MCPServer | None:
        row = self.query_one("#mcp-table", DataTable).cursor_row
        if row is None or not (0 <= row < len(self._servers)):
            return None
        return self._servers[row]

    @on(DataTable.RowHighlighted, "#mcp-table")
    def _row_highlighted(self) -> None:
        server = self._selected()
        if server is not None:
            self._note(f"Selected: {server.name} ({server.type})")

    @on(Button.Pressed, "#add")
    def _add(self) -> None:
        self.app.push_screen(AddMCPScreen())

    @on(Button.Pressed, "#remove")
    def _remove(self) -> None:
        server = self._selected()
        if server is None:
            self.notify("Highlight a server first.", severity="warning")
            return

        def run(log) -> None:
            mcp_manager.remove_server(server.name, log)

        self.app.push_screen(
            ConfirmScreen(
                f"Remove {server.name}",
                "Deletes this entry from ~/.claude.json. Claude Code stops "
                "loading it in new sessions.",
                confirm_label="Remove",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Remove {server.name}", run)),
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


class AddMCPScreen(Screen):
    """A single MCP server: a local command (stdio) or a remote endpoint
    (http)."""

    BINDINGS = [("escape", "back", "Back")]

    TYPE_OPTIONS = [
        ("stdio (local command)", mcp_manager.STDIO),
        ("http (remote server)", mcp_manager.HTTP),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.status_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Add MCP server", classes="screen-title")
        with VerticalScroll(id="add-mcp-form"):
            yield Static(
                "stdio runs a command inside the container; http/sse reaches "
                "a remote server instead. Env/headers: one KEY=value per line.",
                id="add-mcp-note",
            )
            yield Label("Name (used as the key)")
            yield Input(placeholder="e.g. filesystem", id="mcp-name")
            yield Label("Type")
            yield Select(
                self.TYPE_OPTIONS, id="mcp-type", allow_blank=False, value=mcp_manager.STDIO
            )
            yield Label("Command (stdio)")
            yield Input(placeholder="npx", id="mcp-command")
            yield Label("Args (stdio, space-separated)")
            yield Input(
                placeholder="-y @modelcontextprotocol/server-filesystem /home/admin",
                id="mcp-args",
            )
            yield Label("URL (http)")
            yield Input(placeholder="https://mcp.example.com/sse", id="mcp-url")
            yield Label("Env / headers (optional)")
            yield TextArea(id="mcp-env", placeholder="KEY=value")
            yield Static("", id="add-mcp-status")
        with Grid(classes="row2"):
            yield Button("Add", id="submit", variant="success")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def _status(self, message: str) -> None:
        self.status_text = message
        self.query_one("#add-mcp-status", Static).update(message)

    @on(Button.Pressed, "#submit")
    def _submit(self) -> None:
        name = self.query_one("#mcp-name", Input).value.strip()
        type_ = str(self.query_one("#mcp-type", Select).value)
        command = self.query_one("#mcp-command", Input).value
        args_text = self.query_one("#mcp-args", Input).value
        url = self.query_one("#mcp-url", Input).value
        env_text = self.query_one("#mcp-env", TextArea).text

        server, problems = mcp_manager.build_server(name, type_, command, args_text, url, env_text)
        if problems or server is None:
            self._status("\n".join(f"- {p}" for p in problems))
            return

        detail = MCPScreen._detail(server)

        def run(log) -> None:
            mcp_manager.add_server(server, log)

        self.app.push_screen(
            ConfirmScreen(
                f"Add {server.name}",
                f"{server.type}: {detail}\n\n"
                "A server you add can run arbitrary commands or reach "
                "arbitrary URLs on this account's behalf.",
                confirm_label="Add",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Add {server.name}", run)),
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()
