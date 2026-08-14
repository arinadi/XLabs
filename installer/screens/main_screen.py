"""The main menu: Start/Stop the desktop, and the runners behind every
button here that isn't just a screen push (Update, Reset, Clean Cache).
"""

from __future__ import annotations

import os
import shutil

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header

from .. import packages
from .. import start as desktop
from ..const import CACHE_DIR, CONTAINER_NAME, REPO_DIR
from ..system import human_size, is_installed, pull_image, stream_cmd
from .backup_screen import BackupScreen
from .common import ActionScreen, ConfirmScreen, when_confirmed
from .doctor_screen import DoctorScreen
from .settings_screen import SettingsScreen
from .store_screen import StoreScreen

# ── Runners ────────────────────────────────────────────────


def run_start(log) -> None:
    if desktop.start_desktop(log):
        log("")
        log("[bold green]Desktop started.[/bold green] Open the Termux:X11 app to see it.")
    else:
        log("")
        log("[bold red]Desktop did not start.[/bold red] See xfce4.log in the repo.")


def run_stop(log) -> None:
    desktop.stop_desktop(log)


def run_update(log) -> None:
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        log(f"[red]{REPO_DIR} is not a git repository.[/red]")
        return

    log("Pulling latest changes...")
    rc = stream_cmd(f"git -C {REPO_DIR} pull --ff-only", log, timeout=120)
    if rc != 0:
        log("")
        log("Fast-forward failed; resetting to origin/main...")
        stream_cmd(f"git -C {REPO_DIR} fetch origin main", log, timeout=120)
        rc = stream_cmd(f"git -C {REPO_DIR} reset --hard origin/main", log, timeout=60)

    log("")
    if rc == 0:
        log("[green]Up to date.[/green]")
        log("Press Restart to relaunch on the new code, or Back to keep")
        log("running the version already loaded.")
    else:
        log("[red]Update failed.[/red]")


def run_reset(log) -> None:
    # One teardown path. stop_desktop already kills this container's proot
    # tree and verifies, so there is nothing to repeat here.
    log("Stopping the desktop...")
    desktop.stop_desktop(log)
    log("")

    log("Removing container...")
    rc = stream_cmd(f"proot-distro remove {CONTAINER_NAME}", log, timeout=300)
    if rc != 0:
        log("[yellow]Container could not be removed cleanly; continuing.[/yellow]")

    log("")
    ok = pull_image(log)
    if ok:
        packages.reapply_saved_mirror(log)

    log("")
    if ok:
        log("[bold green]Reset complete.[/bold green] Start the desktop from the menu.")
    else:
        log("[bold red]Install failed.[/bold red] Check your connection and try again.")


def run_clean_cache(log) -> None:
    if not os.path.exists(CACHE_DIR):
        log("No cache directory — nothing to clean.")
        return

    log(f"Cache size: {human_size(CACHE_DIR)}")

    log("Stopping the desktop first...")
    desktop.stop_desktop(log)
    log("")

    log("Removing cached image layers...")
    try:
        shutil.rmtree(CACHE_DIR)
    except OSError as e:
        log(f"[red]Failed: {e}[/red]")
        return

    log("")
    log("[green]Cache cleared.[/green] The next install re-downloads the image.")


# ── Main menu ──────────────────────────────────────────────


class MainScreen(Screen):
    BINDINGS = [("q", "app.quit", "Quit")]

    # Short labels keep three to a row; the full meaning lives in the tooltip.
    TOOLTIPS = {
        "update": "Pull the latest XLabs",
        "store": "Search and install packages in the container",
        "settings": "Per-device preferences, saved to .env",
        "doctor": "Diagnose and repair the environment",
        "backup": "Back up or restore your home directory",
        "reset": "Delete the container and reinstall it",
        "cache": "Delete downloaded image layers",
    }

    def on_mount(self) -> None:
        for button_id, text in self.TOOLTIPS.items():
            self.query_one(f"#{button_id}", Button).tooltip = text

    def compose(self) -> ComposeResult:
        yield Header()
        # Grid rather than Horizontal: a row of 1fr children in a Horizontal
        # gave every button the full remaining width instead of a share, so
        # three-button rows ran off the side of the screen.
        # The two actions that carry a full sentence get half the width each;
        # the rest are one word and fit three to a row even on a narrow phone.
        with VerticalScroll(id="menu"):
            with Grid(classes="row2"):
                yield Button("Start Desktop", id="start", variant="success")
                yield Button("Stop Desktop", id="stop", variant="warning")
            with Grid(classes="row3"):
                yield Button("Update", id="update")
                yield Button("Store", id="store")
                yield Button("Settings", id="settings")
            with Grid(classes="row2"):
                yield Button("Doctor", id="doctor")
                yield Button("Backup", id="backup")
            with Grid(classes="row2"):
                yield Button("Reset", id="reset", variant="error")
                yield Button("Cache", id="cache")
        yield Footer()

    @on(Button.Pressed, "#start")
    def _start(self) -> None:
        if not is_installed():
            self.app.push_screen(
                ConfirmScreen(
                    "Container not installed",
                    "No Debian container found. Pull it now?\n\n"
                    "This downloads the container image and takes a few "
                    "minutes.",
                    confirm_label="Install",
                ),
                when_confirmed(self.app, lambda: ActionScreen("Install", run_reset)),
            )
            return
        self.app.push_screen(ActionScreen("Start Desktop", run_start))

    @on(Button.Pressed, "#stop")
    def _stop(self) -> None:
        self.app.push_screen(ActionScreen("Stop Desktop", run_stop))

    @on(Button.Pressed, "#update")
    def _update(self) -> None:
        self.app.push_screen(ActionScreen("Update", run_update, offer_restart=True))

    @on(Button.Pressed, "#store")
    def _store(self) -> None:
        self.app.push_screen(StoreScreen())

    @on(Button.Pressed, "#settings")
    def _settings(self) -> None:
        self.app.push_screen(SettingsScreen())

    @on(Button.Pressed, "#doctor")
    def _doctor(self) -> None:
        self.app.push_screen(DoctorScreen())

    @on(Button.Pressed, "#backup")
    def _backup(self) -> None:
        self.app.push_screen(BackupScreen())

    @on(Button.Pressed, "#reset")
    def _reset(self) -> None:
        self.app.push_screen(
            ConfirmScreen(
                "Reset (Clean Install)",
                "This deletes the entire container and pulls a fresh image.\n\n"
                "Every file, setting, and package inside the container is lost "
                "permanently. Your Termux home is untouched. Back up first from "
                "the Backup screen if you want to keep your files.",
                confirm_label="Delete and reinstall",
            ),
            when_confirmed(self.app, lambda: ActionScreen("Reset", run_reset)),
        )

    @on(Button.Pressed, "#cache")
    def _cache(self) -> None:
        self.app.push_screen(
            ConfirmScreen(
                "Clean Image Cache",
                "Deletes downloaded OCI image layers. The container itself is "
                "kept; the next install re-downloads the image.",
                confirm_label="Delete cache",
            ),
            when_confirmed(self.app, lambda: ActionScreen("Clean Image Cache", run_clean_cache)),
        )
