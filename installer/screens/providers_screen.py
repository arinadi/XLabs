"""Claude Code accounts: the official Anthropic login, or a saved gateway
profile written into the container's ~/.claude/settings.json.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from .. import providers
from ..system import is_installed
from .common import ActionScreen, ConfirmScreen, ScrollableTable, when_confirmed


class ProvidersScreen(Screen):
    """Claude Code accounts: the official Anthropic login, or a saved
    gateway profile written into the container's ~/.claude/settings.json.

    Only one is active inside the container at a time.
    """

    BINDINGS = [("escape", "back", "Back")]

    NOTE = (
        "Activating a provider rewrites ~/.claude/settings.json inside the "
        "container. Official clears the gateway keys so Claude Code falls "
        "back to your claude.ai / Console login."
    )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Claude Code providers", classes="screen-title")
        yield Static(self.NOTE, id="providers-note")
        yield ScrollableTable(id="providers-table", cursor_type="row", zebra_stripes=True)
        with Grid(classes="row3"):
            yield Button("Add", id="add", variant="success")
            yield Button("Activate", id="activate")
            yield Button("Remove", id="remove", variant="error")
        yield Button("Back", id="back", variant="primary")
        yield Footer()

    def __init__(self) -> None:
        super().__init__()
        # Row order behind the table: OFFICIAL first, then saved providers.
        self._rows: list[str] = []
        self.status_text = self.NOTE

    def _note(self, message: str) -> None:
        self.status_text = message
        self.query_one("#providers-note", Static).update(message)

    def on_mount(self) -> None:
        self.query_one("#providers-table", DataTable).add_columns("", "Name", "Base URL")
        if not is_installed():
            self._note("No container yet — install it first from the main menu.")
        self._fill()

    def on_screen_resume(self) -> None:
        self._fill()

    def _fill(self) -> None:
        active = providers.active_provider_name()
        saved = providers.list_providers()
        self._rows = [providers.OFFICIAL] + [p.name for p in saved]

        table = self.query_one("#providers-table", DataTable)
        table.clear()
        mark = "[green]on[/green]" if active == providers.OFFICIAL else ""
        table.add_row(mark, "Official", "claude.ai / Anthropic Console login")
        for p in saved:
            mark = "[green]on[/green]" if active == p.name else ""
            table.add_row(mark, p.name, p.base_url)
        self._note(self.NOTE)

    def _selected(self) -> str | None:
        row = self.query_one("#providers-table", DataTable).cursor_row
        if row is None or not (0 <= row < len(self._rows)):
            return None
        return self._rows[row]

    @on(DataTable.RowHighlighted, "#providers-table")
    def _row_highlighted(self) -> None:
        name = self._selected()
        if name is not None:
            label = "Official" if name == providers.OFFICIAL else name
            state = "active" if name == providers.active_provider_name() else "not active"
            self._note(f"Selected: {label} ({state})")

    @on(Button.Pressed, "#add")
    def _add(self) -> None:
        self.app.push_screen(AddProviderScreen())

    @on(Button.Pressed, "#activate")
    def _activate(self) -> None:
        name = self._selected()
        if name is None:
            self.notify("Highlight a provider first.", severity="warning")
            return
        label = "Official" if name == providers.OFFICIAL else name
        if name == providers.active_provider_name():
            self.notify(f"{label} is already active.", severity="warning")
            return
        if not is_installed():
            self.notify("No container to update.", severity="warning")
            return

        def run(log) -> None:
            providers.activate(name, log)

        if name == providers.OFFICIAL:
            body = "claude.ai / Anthropic Console login."
        else:
            provider = providers.provider_by_name(name)
            body = provider.base_url if provider else ""

        self.app.push_screen(
            ConfirmScreen(
                f"Activate {label}",
                f"{body}\n\nRewrites ~/.claude/settings.json inside the container.",
                confirm_label="Activate",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Activate {label}", run)),
        )

    @on(Button.Pressed, "#remove")
    def _remove(self) -> None:
        name = self._selected()
        if name is None:
            self.notify("Highlight a provider first.", severity="warning")
            return
        if name == providers.OFFICIAL:
            self.notify("Official is built in and cannot be removed.", severity="warning")
            return

        def run(log) -> None:
            if providers.active_provider_name() == name and is_installed():
                providers.activate(providers.OFFICIAL, log)
            if providers.remove_provider(name):
                log(f"Removed {name}.")
            else:
                log(f"[red]Could not remove {name}.[/red]")

        self.app.push_screen(
            ConfirmScreen(
                f"Remove {name}",
                "Deletes the saved base URL and token. If it is the active "
                "provider, Official is activated first.",
                confirm_label="Remove",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Remove {name}", run)),
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


class AddProviderScreen(Screen):
    """A gateway/LiteLLM-style provider: base URL, token, and optional
    model-name overrides for a gateway that doesn't recognise Anthropic's
    own model names."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self.status_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Add provider", classes="screen-title")
        with VerticalScroll(id="add-provider-form"):
            yield Static(
                "Base URL and token are sent as ANTHROPIC_BASE_URL / "
                "ANTHROPIC_AUTH_TOKEN. Leave model mapping blank unless the "
                "gateway rejects Anthropic's own model names.",
                id="add-provider-note",
            )
            yield Label("Name (used as the key)")
            yield Input(placeholder="e.g. work-gateway", id="provider-name")
            yield Label("Base URL")
            yield Input(placeholder="https://llm-gateway.example.com", id="provider-base-url")
            yield Label("Auth token")
            yield Input(placeholder="sk-gateway-...", password=True, id="provider-token")
            yield Label("Opus model override (optional)")
            yield Input(placeholder="your-large-model", id="provider-opus")
            yield Label("Sonnet model override (optional)")
            yield Input(placeholder="your-mid-model", id="provider-sonnet")
            yield Label("Haiku model override (optional)")
            yield Input(placeholder="your-small-model", id="provider-haiku")
            yield Static("", id="add-provider-status")
        with Grid(classes="row2"):
            yield Button("Add", id="submit", variant="success")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def _status(self, message: str) -> None:
        self.status_text = message
        self.query_one("#add-provider-status", Static).update(message)

    @on(Button.Pressed, "#submit")
    def _submit(self) -> None:
        name = self.query_one("#provider-name", Input).value.strip()
        base_url = self.query_one("#provider-base-url", Input).value.strip()
        token = self.query_one("#provider-token", Input).value.strip()
        opus = self.query_one("#provider-opus", Input).value.strip()
        sonnet = self.query_one("#provider-sonnet", Input).value.strip()
        haiku = self.query_one("#provider-haiku", Input).value.strip()

        problems = providers.validate_provider(name, base_url, token)
        if problems:
            self._status("\n".join(f"- {p}" for p in problems))
            return

        provider = providers.Provider(name, base_url, token, opus, sonnet, haiku)
        if not providers.add_provider(provider):
            self._status("Could not save the provider.")
            return

        self.notify(f"Added {name}. Activate it from the Providers list.")
        self.app.pop_screen()

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()
