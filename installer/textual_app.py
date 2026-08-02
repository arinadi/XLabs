"""Textual TUI for arinanoLabs — flicker-free single screen."""

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, Static, Label, Button, RichLog
)
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive


# ── Styles ─────────────────────────────────────────────────

CSS = """
Screen {
    background: $surface;
}

#main {
    width: 100%;
    height: 100%;
    align: center top;
    padding: 1 0;
}

#content {
    width: 44;
    height: auto;
    border: heavy $accent;
    padding: 1 2;
}

#content-title {
    text-style: bold;
    color: $accent;
    text-align: center;
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

.menu-btn { width: 100%; margin: 0 0 1 0; }
#start { background: $accent; color: $text; }
#stop { background: $warning; color: $text; }
#back { width: 100%; margin: 1 0 0 0; }
"""


class ArinanoLabsApp(App):
    """Main TUI — single screen, no push/pop."""

    TITLE = "arinanoLabs"
    CSS = CSS

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("escape", "back", "Back"),
        ("1", "action_start", "Start"),
        ("2", "action_stop", "Stop"),
        ("3", "action_update", "Update"),
        ("4", "action_tools", "Tools"),
        ("5", "action_status", "Status"),
    ]

    view = reactive("menu")

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main"):
            yield Vertical(id="content")
        yield Footer()

    def on_mount(self):
        self.show_menu()

    def _set_content(self, *widgets):
        """Replace content without flicker."""
        content = self.query_one("#content")
        content.remove_children()
        content.mount(*widgets)

    # ── Menu ───────────────────────────────────────────────

    def show_menu(self):
        from .ui import get_version
        self.view = "menu"
        self._set_content(
            Label("📱 arinanoLabs", id="content-title"),
            Label(f"v{get_version()}", id="version"),
            Static(),
            Button("▶️  Start Desktop", id="start", variant="primary", classes="menu-btn"),
            Button("⏹️  Stop Desktop", id="stop", variant="warning", classes="menu-btn"),
            Button("🔄  Update", id="update", classes="menu-btn"),
            Button("🧰  Extra Tools", id="tools", classes="menu-btn"),
            Button("📊  Status", id="status", classes="menu-btn"),
            Static(),
            Button("🚪  Exit", id="exit", variant="default", classes="menu-btn"),
        )

    # ── Actions ────────────────────────────────────────────

    def action_start(self):
        if self.view != "menu":
            return
        self.view = "start"
        self._set_content(
            Label("▶️  Starting desktop...", id="content-title"),
            Static(),
            RichLog(id="log", auto_scroll=True),
            Button("Back", id="back"),
        )
        self.run_worker(self._do_start)

    async def _do_start(self):
        from .start import start_desktop
        log = self.query_one("#log", RichLog)
        log.write("[cyan]→ Starting PulseAudio...[/cyan]")
        log.write("[cyan]→ Starting virgl...[/cyan]")
        log.write("[cyan]→ Starting X11...[/cyan]")
        log.write("[cyan]→ Launching MATE...[/cyan]")
        success = start_desktop()
        if success:
            log.write("[green]✓ Desktop started![/green]")
            log.write("[dim]Open Termux:X11 app[/dim]")
        else:
            log.write("[red]✗ Failed to start desktop[/red]")

    def action_stop(self):
        if self.view != "menu":
            return
        self.view = "stop"
        self._set_content(
            Label("⏹️  Stopping desktop...", id="content-title"),
            Static(),
            RichLog(id="log", auto_scroll=True),
            Button("Back", id="back"),
        )
        from .start import stop_desktop
        log = self.query_one("#log", RichLog)
        log.write("[yellow]Stopping processes...[/yellow]")
        stop_desktop()
        log.write("[green]✓ Desktop stopped[/green]")

    def action_update(self):
        if self.view != "menu":
            return
        self.view = "update"
        self._set_content(
            Label("🔄  Updating...", id="content-title"),
            Static(),
            RichLog(id="log", auto_scroll=True),
            Button("Back", id="back"),
        )
        self.run_worker(self._do_update)

    async def _do_update(self):
        import subprocess
        import os
        log = self.query_one("#log", RichLog)
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if not os.path.exists(os.path.join(repo_dir, ".git")):
            log.write("[red]✗ Not a git repository[/red]")
            return

        log.write("[cyan]→ Pulling latest changes...[/cyan]")
        result = subprocess.run(
            ["git", "pull"],
            cwd=repo_dir, capture_output=True, text=True
        )

        if result.returncode != 0:
            log.write("[dim]Fetching latest...[/dim]")
            subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_dir, capture_output=True)
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

    def action_tools(self):
        if self.view != "menu":
            return
        self.view = "tools"
        self._set_content(
            Label("🧰  Extra Tools", id="content-title"),
            Static(),
            Button("Chromium Browser", id="chromium", classes="menu-btn"),
            Button("VS Code (code-server)", id="vscode", classes="menu-btn"),
            Button("Zsh + Oh My Zsh", id="zsh", classes="menu-btn"),
            Button("Neovim", id="neovim", classes="menu-btn"),
            Button("GitHub CLI", id="gh", classes="menu-btn"),
            Static(),
            Button("Back", id="back"),
        )

    def action_status(self):
        if self.view != "menu":
            return
        self.view = "status"
        from .start import is_running
        from .ui import is_installed, get_version
        from .gpu import detect_gpu, get_gpu_summary

        container = is_installed()
        running = is_running()
        gpu = detect_gpu()

        self._set_content(
            Label("📊  System Status", id="content-title"),
            Static(),
            Label(f"  Container:  {'✓ Installed' if container else '✗ Not found'}"),
            Label(f"  Desktop:    {'● Running' if running else '○ Not running'}"),
            Label(f"  GPU:        {get_gpu_summary(gpu)}"),
            Label(f"  Version:    {get_version()}"),
            Static(),
            Button("Back", id="back"),
        )

    # ── Button handler ─────────────────────────────────────

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed):
        if event.button.id == "exit":
            self.exit()
        elif event.button.id == "back":
            self.show_menu()
        elif event.button.id == "start":
            self.action_start()
        elif event.button.id == "stop":
            self.action_stop()
        elif event.button.id == "update":
            self.action_update()
        elif event.button.id == "tools":
            self.action_tools()
        elif event.button.id == "status":
            self.action_status()

    def action_back(self):
        if self.view != "menu":
            self.show_menu()


def run_textual():
    """Run the Textual TUI."""
    app = ArinanoLabsApp()
    app.run()
