"""Per-device preferences, stored in .env.

Each value is owned by whatever module actually uses it — audio.py, bench.py,
start.py, packages.py — this screen only reads and writes them through those
modules' own functions. Mirror is shown but not edited here: Store -> Mirror
already measures candidates and picking one there saves it the same way, so
a second editable copy here would just be two places that could disagree.
"""

from __future__ import annotations

import os
import shutil

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.widgets import Button, Footer, Header, Label, Select, Static

from .. import audio, bench, isolation, packages
from .. import start as desktop
from ..const import CACHE_DIR, CONTAINER_NAME, REPO_DIR
from ..system import get_version, stream_cmd, unlink_launcher
from .claude_md_screen import ClaudeMdScreen
from .common import ActionScreen, ConfirmScreen, CopyableScreen, when_confirmed
from .mcp_screen import MCPScreen
from .providers_screen import ProvidersScreen


def run_uninstall(log) -> None:
    # Same teardown as Reset, minus the reinstall, plus the launcher — Reset
    # leaves `xlabs` on PATH because it always reinstalls; uninstall does not.
    log("Stopping the desktop...")
    desktop.stop_desktop(log)
    log("")

    log("Removing container...")
    rc = stream_cmd(f"proot-distro remove {CONTAINER_NAME}", log, timeout=300)
    if rc != 0:
        log("[yellow]Container could not be removed cleanly; continuing.[/yellow]")
    log("")

    if os.path.exists(CACHE_DIR):
        log("Removing cached image layers...")
        try:
            shutil.rmtree(CACHE_DIR)
        except OSError as e:
            log(f"[yellow]Could not remove cache: {e}[/yellow]")
    log("")

    log("Removing launcher...")
    removed = unlink_launcher()
    for link in removed:
        log(f"  removed {link}")
    if not removed:
        log("  nothing on PATH to remove")

    log("")
    log("[bold green]Uninstalled.[/bold green] The container, cache, and "
        f"launcher are gone. {REPO_DIR} was left in place — remove it "
        "yourself with `rm -rf ~/XLabs` if you want it gone too.")


class SettingsScreen(CopyableScreen):
    """Per-device preferences, stored in .env.

    Each value is owned by whatever module actually uses it — audio.py,
    bench.py, start.py, packages.py — this screen only reads and writes
    them through those modules' own functions. Mirror is shown but not
    edited here: Store -> Mirror already measures candidates and picking
    one there saves it the same way, so a second editable copy here would
    just be two places that could disagree.
    """

    BINDINGS = [("escape", "back", "Back")]

    DRAW_PATH_OPTIONS = [
        ("Normal", "normal"),
        ("Legacy drawing (fixes some black screens)", "legacy-drawing"),
        ("Force BGRA (fixes swapped colors)", "force-bgra"),
        ("Legacy drawing + force BGRA", "legacy-drawing+force-bgra"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.status_text = ""
        # Last value _refresh() itself set, per Select — Select.Changed is
        # a posted message, dispatched after _refresh() has already
        # returned, so a "loading" flag reset at the end of _refresh()
        # cannot reliably guard against it. Comparing against what was
        # just assigned works regardless of when the message lands.
        self._last_audio = ""
        self._last_gpu = ""
        self._last_x11 = ""
        self._last_isolation = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Settings", classes="screen-title")
        with VerticalScroll(id="settings-form"):
            yield Static(
                "Saved to .env — restart the desktop for changes to take effect.",
                id="settings-note",
            )
            yield Static("", id="settings-mirror")
            yield Label("Rendering & audio", classes="settings-section")
            yield Label("Audio method")
            yield Select(
                [(m.description, m.name) for m in audio.METHODS],
                id="settings-audio",
                allow_blank=False,
            )
            yield Label("GPU profile")
            yield Select(
                [(p.description, p.name) for p in bench.PRESETS],
                id="settings-gpu",
                allow_blank=False,
            )
            yield Label("termux-x11 rendering")
            yield Select(self.DRAW_PATH_OPTIONS, id="settings-x11", allow_blank=False)
            yield Label("Container", classes="settings-section")
            yield Label("Isolation")
            yield Select(
                [(p.description, p.name) for p in isolation.PRESETS],
                id="settings-isolation",
                allow_blank=False,
            )
            yield Label("Claude Code", classes="settings-section")
            yield Button("Providers", id="claude-providers", variant="warning")
            yield Button("MCP servers", id="claude-mcp")
            yield Button("CLAUDE.md editor", id="claude-md")
            yield Static("", id="settings-status")
            yield Label("Danger zone", classes="settings-section settings-danger-label")
            yield Button("Uninstall XLabs", id="uninstall", variant="error")
        with Grid(classes="row2"):
            yield Button("C", id="copy")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#copy", Button).tooltip = "Copy these settings"
        self.query_one("#uninstall", Button).tooltip = (
            "Remove the container, cache, and xlabs launcher"
        )
        self.query_one("#settings-isolation", Select).tooltip = (
            "Measure which preset is fastest from Doctor -> Tools -> IO"
        )
        self.query_one("#claude-providers", Button).tooltip = (
            "Switch which Claude Code account/gateway is active in the container"
        )
        self.query_one("#claude-mcp", Button).tooltip = (
            "Add or remove MCP servers, loaded in every Claude Code session"
        )
        self.query_one("#claude-md", Button).tooltip = (
            "Edit ~/.claude/CLAUDE.md, Claude Code's global memory file"
        )
        self._refresh()

    def on_screen_resume(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        mirror = packages.current_mirror() or "no sources file yet"
        self.query_one("#settings-mirror", Static).update(
            f"Mirror: {mirror} · change from Store → Mirror"
        )
        self._last_audio = audio.load_method().name
        self.query_one("#settings-audio", Select).value = self._last_audio
        # No benchmark has necessarily run yet, unlike audio/X11 which
        # always have a real default — fall back to the same baseline
        # Bench itself would rather than leave the select blank.
        self._last_gpu = (bench.load_profile() or bench.PRESETS[0]).name
        self.query_one("#settings-gpu", Select).value = self._last_gpu
        self._last_x11 = desktop.load_draw_path()
        self.query_one("#settings-x11", Select).value = self._last_x11
        self._last_isolation = isolation.load_preset().name
        self.query_one("#settings-isolation", Select).value = self._last_isolation

    def _status(self, message: str) -> None:
        self.status_text = message
        self.query_one("#settings-status", Static).update(message)

    @on(Select.Changed, "#settings-audio")
    def _audio_changed(self, event: Select.Changed) -> None:
        if str(event.value) == self._last_audio:
            return
        method = audio.method_by_name(str(event.value))
        if method is not None:
            self._last_audio = method.name
            audio.save_method(method)
            self._status(f"Audio method set to {method.name}.")

    @on(Select.Changed, "#settings-gpu")
    def _gpu_changed(self, event: Select.Changed) -> None:
        if str(event.value) == self._last_gpu:
            return
        preset = bench.preset_by_name(str(event.value))
        if preset is not None:
            self._last_gpu = preset.name
            bench.set_profile_manually(preset)
            self._status(f"GPU profile set to {preset.name}.")

    @on(Select.Changed, "#settings-x11")
    def _x11_changed(self, event: Select.Changed) -> None:
        if str(event.value) == self._last_x11:
            return
        self._last_x11 = str(event.value)
        desktop.save_draw_path(self._last_x11)
        self._status("termux-x11 rendering mode saved.")

    @on(Select.Changed, "#settings-isolation")
    def _isolation_changed(self, event: Select.Changed) -> None:
        if str(event.value) == self._last_isolation:
            return
        preset = isolation.preset_by_name(str(event.value))
        if preset is not None:
            self._last_isolation = preset.name
            isolation.set_preset_manually(preset)
            self._status(f"Container isolation set to {preset.name}.")

    def copy_payload(self) -> str:
        return "\n".join(
            [
                f"XLabs settings - {get_version()}",
                "",
                f"Mirror:  {packages.current_mirror() or 'unknown'}",
                f"Audio:   {audio.load_method().name}",
                f"GPU:     {(bench.load_profile() or bench.PRESETS[0]).name}",
                f"X11:     {desktop.load_draw_path()}",
                f"Isolation: {isolation.load_preset().name}",
            ]
        )

    @on(Button.Pressed, "#uninstall")
    def _uninstall(self) -> None:
        self.app.push_screen(
            ConfirmScreen(
                "Uninstall XLabs",
                "This deletes the container and its cached image layers, and "
                "removes the xlabs launcher from PATH.\n\n"
                f"{REPO_DIR} and any backups in ~/XLabs-backups are left in "
                "place. Every file, setting, and package inside the "
                "container is lost permanently — back up first from the "
                "Backup screen if you want to keep your files.",
                confirm_label="Uninstall",
            ),
            when_confirmed(self.app, lambda: ActionScreen("Uninstall", run_uninstall)),
        )

    @on(Button.Pressed, "#claude-providers")
    def _providers(self) -> None:
        self.app.push_screen(ProvidersScreen())

    @on(Button.Pressed, "#claude-mcp")
    def _mcp(self) -> None:
        self.app.push_screen(MCPScreen())

    @on(Button.Pressed, "#claude-md")
    def _claude_md(self) -> None:
        self.app.push_screen(ClaudeMdScreen())

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()
