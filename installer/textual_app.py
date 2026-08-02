"""Textual TUI for arinanoLabs — redesigned."""

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, Static, Label, Button, DataTable,
    ProgressBar, RichLog
)
from textual.containers import Vertical, Horizontal, Center
from textual.screen import ModalScreen
from textual import on, work
from textual.reactive import reactive

from .ui import is_installed, get_version, PROOT_DIR
from .gpu import detect_gpu, get_gpu_summary


# ── Styles ─────────────────────────────────────────────────

CSS = """
Screen {
    background: $surface;
}

#menu-title {
    text-align: center;
    width: 100%;
    padding: 1 0 0 0;
    color: $accent;
    text-style: bold;
}

#version {
    text-align: center;
    width: 100%;
    color: $text-muted;
    padding: 0 0 1 0;
}

.menu-buttons {
    width: 100%;
    height: auto;
    align: center middle;
    padding: 0 4;
}

.menu-buttons Button {
    width: 100%;
    margin: 0 0 1 0;
    height: 3;
}

#start { background: $accent; color: $text; }
#stop { background: $warning; color: $text; }

.status-table {
    width: 100%;
    padding: 1 4;
}

 ConfirmDialog {
    align: center middle;
}

 ConfirmDialog > Static {
    width: 50%;
    height: auto;
    border: tall $accent;
    padding: 1 2;
    background: $surface;
}

 ConfirmDialog Button {
    margin: 0 1;
}
"""


class ConfirmDialog(ModalScreen):
    """Confirmation modal."""

    CSS = """
    ConfirmDialog {
        align: center middle;
    }
    #confirm-box {
        width: 50;
        height: auto;
        border: tall $accent;
        padding: 1 2;
        background: $surface;
    }
    #confirm-buttons {
        width: 100%;
        align: center middle;
        padding: 1 0 0 0;
    }
    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, message: str, callback=None):
        super().__init__()
        self.message = message
        self.callback = callback

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static(self.message)
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes", id="yes", variant="error")
                yield Button("No", id="no", variant="default")

    @on(Button.Pressed, "#yes")
    def on_yes(self):
        if self.callback:
            self.callback()
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def on_no(self):
        self.dismiss(False)


class MenuScreen(ModalScreen):
    """Main menu screen."""

    CSS = """
    MenuScreen {
        align: center middle;
    }
    #menu-box {
        width: 44;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
        background: $surface;
    }
    #menu-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        padding: 0 0 1 0;
    }
    #version {
        text-align: center;
        color: $text-muted;
        padding: 0 0 1 0;
    }
    Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
        ("1", "start", "Start"),
        ("2", "stop", "Stop"),
        ("3", "update", "Update"),
        ("4", "tools", "Tools"),
        ("5", "status", "Status"),
        ("6", "uninstall", "Uninstall"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-box"):
            yield Label("📱 arinanoLabs", id="menu-title")
            yield Label(f"v{get_version()}", id="version")
            yield Static()
            yield Button("▶️  Start Desktop", id="start", variant="primary")
            yield Button("⏹️  Stop Desktop", id="stop", variant="warning")
            yield Button("🔄  Update", id="update")
            yield Button("🧰  Extra Tools", id="tools")
            yield Button("📊  Status", id="status")
            yield Button("🗑️   Uninstall", id="uninstall", variant="error")
            yield Static()
            yield Button("🚪  Exit", id="exit", variant="default")

    @on(Button.Pressed, "#start")
    def handle_start(self):
        self.app.push_screen(StartScreen())

    @on(Button.Pressed, "#stop")
    def handle_stop(self):
        self.app.push_screen(StopScreen())

    @on(Button.Pressed, "#update")
    def handle_update(self):
        self.app.push_screen(UpdateScreen())

    @on(Button.Pressed, "#tools")
    def handle_tools(self):
        self.app.push_screen(ToolsScreen())

    @on(Button.Pressed, "#status")
    def handle_status(self):
        self.app.push_screen(StatusScreen())

    @on(Button.Pressed, "#uninstall")
    def handle_uninstall(self):
        def confirm():
            self.app.push_screen(UninstallScreen())
        self.app.push_screen(
            ConfirmDialog("⚠️ Remove arinanoLabs completely?", confirm)
        )

    @on(Button.Pressed, "#exit")
    def handle_exit(self):
        self.app.exit()


class StartScreen(ModalScreen):
    """Start desktop screen."""

    CSS = """
    #start-box {
        width: 50;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="start-box"):
            yield Label("▶️  Starting desktop...", id="start-title")
            yield Static()
            yield RichLog(id="start-log", auto_scroll=True)

    def on_mount(self):
        self.run_worker(self._start_desktop)

    async def _start_desktop(self):
        from .start import start_desktop
        log = self.query_one("#start-log", RichLog)
        log.write("[cyan]Starting PulseAudio...[/cyan]")
        log.write("[cyan]Starting virgl...[/cyan]")
        log.write("[cyan]Starting X11...[/cyan]")
        log.write("[cyan]Launching MATE...[/cyan]")
        success = start_desktop()
        if success:
            log.write("[green]✓ Desktop started![/green]")
            log.write("[dim]Open Termux:X11 app[/dim]")
        else:
            log.write("[red]✗ Failed to start desktop[/red]")
        yield Button("Back", id="back")

    @on(Button.Pressed, "#back")
    def handle_back(self):
        self.app.pop_screen()


class StopScreen(ModalScreen):
    """Stop desktop screen."""

    CSS = """
    #stop-box {
        width: 50;
        height: auto;
        border: heavy $warning;
        padding: 1 2;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="stop-box"):
            yield Label("⏹️  Stopping desktop...")
            yield Static()
            yield RichLog(id="stop-log", auto_scroll=True)
            yield Button("Back", id="back")

    def on_mount(self):
        from .start import stop_desktop
        log = self.query_one("#stop-log", RichLog)
        log.write("[yellow]Stopping processes...[/yellow]")
        stop_desktop()
        log.write("[green]✓ Desktop stopped[/green]")

    @on(Button.Pressed, "#back")
    def handle_back(self):
        self.app.pop_screen()


class UpdateScreen(ModalScreen):
    """Update screen."""

    CSS = """
    #update-box {
        width: 50;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="update-box"):
            yield Label("🔄  Updating...")
            yield Static()
            yield RichLog(id="update-log", auto_scroll=True)
            yield Button("Back", id="back")

    def on_mount(self):
        self.run_worker(self._do_update)

    async def _do_update(self):
        import subprocess
        import os
        log = self.query_one("#update-log", RichLog)

        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.exists(os.path.join(repo_dir, ".git")):
            log.write("[red]✗ Not a git repository[/red]")
            return

        log.write("[cyan]Pulling latest changes...[/cyan]")
        result = subprocess.run(
            ["git", "pull", "--ff-only", "--depth=1"],
            cwd=repo_dir, capture_output=True, text=True
        )

        if result.returncode != 0:
            log.write("[dim]Fetching latest...[/dim]")
            subprocess.run(["git", "fetch", "--depth=1", "origin", "main"], cwd=repo_dir, capture_output=True)
            result = subprocess.run(
                ["git", "reset", "--hard", "origin/main"],
                cwd=repo_dir, capture_output=True, text=True
            )

        if result.returncode == 0:
            if "Already up to date" in result.stdout:
                log.write("[green]✓ Already on latest version[/green]")
            else:
                log.write("[green]✓ Updated![/green]")
                log.write("[dim]Restart alabs to use new version[/dim]")
        else:
            log.write("[red]✗ Update failed[/red]")

    @on(Button.Pressed, "#back")
    def handle_back(self):
        self.app.pop_screen()


class ToolsScreen(ModalScreen):
    """Extra tools screen."""

    CSS = """
    #tools-box {
        width: 44;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
        background: $surface;
    }
    Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="tools-box"):
            yield Label("🧰  Extra Tools", id="tools-title")
            yield Static()
            yield Button("Chromium Browser", id="chromium")
            yield Button("VS Code (code-server)", id="vscode")
            yield Button("Zsh + Oh My Zsh", id="zsh")
            yield Button("Neovim", id="neovim")
            yield Button("GitHub CLI", id="gh")
            yield Static()
            yield Button("Back", id="back")

    @on(Button.Pressed)
    def handle_tool(self, event: Button.Pressed):
        # TODO: implement tool installation
        pass

    @on(Button.Pressed, "#back")
    def handle_back(self):
        self.app.pop_screen()


class StatusScreen(ModalScreen):
    """System status screen."""

    CSS = """
    #status-box {
        width: 50;
        height: auto;
        border: heavy $accent;
        padding: 1 2;
        background: $surface;
    }
    #status-title {
        text-style: bold;
        color: $accent;
    }
    """

    def compose(self) -> ComposeResult:
        from .start import is_running

        container_exists = is_installed()
        running = is_running()
        gpu = detect_gpu()

        status_items = [
            f"  Container:  {'✓ Installed' if container_exists else '✗ Not found'}",
            f"  Desktop:    {'● Running' if running else '○ Not running'}",
            f"  GPU:        {get_gpu_summary(gpu)}",
            f"  Version:    {get_version()}",
        ]

        with Vertical(id="status-box"):
            yield Label("📊  System Status", id="status-title")
            yield Static()
            for item in status_items:
                yield Label(item)
            yield Static()
            yield Button("Back", id="back")

    @on(Button.Pressed, "#back")
    def handle_back(self):
        self.app.pop_screen()


class UninstallScreen(ModalScreen):
    """Uninstall screen."""

    CSS = """
    #uninstall-box {
        width: 50;
        height: auto;
        border: heavy $error;
        padding: 1 2;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="uninstall-box"):
            yield Label("🗑️  Uninstalling...")
            yield Static()
            yield RichLog(id="uninstall-log", auto_scroll=True)
            yield Button("Back", id="back")

    def on_mount(self):
        log = self.query_one("#uninstall-log", RichLog)
        log.write("[red]Uninstall not yet implemented[/red]")
        log.write("[dim]Coming soon[/dim]")

    @on(Button.Pressed, "#back")
    def handle_back(self):
        self.app.pop_screen()


class ArinanoLabsApp(App):
    """Main TUI Application."""

    TITLE = "arinanoLabs"
    SUB_TITLE = "Linux on Android"

    CSS = CSS

    def compose(self) -> ComposeResult:
        yield Header()
        yield MenuScreen()
        yield Footer()


def run_textual():
    """Run the Textual TUI."""
    app = ArinanoLabsApp()
    app.run()
