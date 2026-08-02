"""Textual TUI for arinanoLabs."""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Label, Button
from textual.containers import Vertical, Horizontal
from textual import on


class MenuScreen(Static):
    """Main menu screen."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("  [bold]Main Menu[/bold]", id="title")
            yield Static()
            yield Button("▶️  Start Desktop", id="start", variant="primary")
            yield Button("⏹️  Stop Desktop", id="stop", variant="warning")
            yield Button("🔄  Update", id="update")
            yield Button("🧰  Extra Tools", id="tools")
            yield Button("📊  Status", id="status")
            yield Button("🗑️   Uninstall", id="uninstall", variant="error")
            yield Static()
            yield Button("🚪  Exit", id="exit", variant="default")


class ArinanoLabsApp(App):
    """arinaLabs TUI Application."""

    CSS = """
    Screen {
        layout: vertical;
        align: center middle;
    }
    #title {
        width: 100%;
        text-align: center;
        padding: 1 0;
    }
    Button {
        width: 40;
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield MenuScreen()
        yield Footer()

    @on(Button.Pressed, "#start")
    def handle_start(self):
        self.run_action("quit")
        from .start import start_desktop
        start_desktop()

    @on(Button.Pressed, "#stop")
    def handle_stop(self):
        self.run_action("quit")
        from .start import stop_desktop
        stop_desktop()

    @on(Button.Pressed, "#update")
    def handle_update(self):
        self.run_action("quit")
        from .menu import handle_update
        handle_update()

    @on(Button.Pressed, "#tools")
    def handle_tools(self):
        self.run_action("quit")
        from .menu import handle_tools
        handle_tools()

    @on(Button.Pressed, "#status")
    def handle_status(self):
        self.run_action("quit")
        from .menu import handle_status
        handle_status()

    @on(Button.Pressed, "#uninstall")
    def handle_uninstall(self):
        self.run_action("quit")
        from .menu import handle_uninstall
        handle_uninstall()


def run_textual():
    """Run the Textual TUI."""
    app = ArinanoLabsApp()
    app.run()
