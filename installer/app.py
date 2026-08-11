"""arinanoLabs TUI.

Textual app. Every menu entry runs its work in a thread worker and streams
output into a log pane, so the UI stays responsive while apt or proot-distro
takes minutes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
)

from . import doctor
from . import packages
from . import start as desktop
from .const import CACHE_DIR, CONTAINER_NAME, IMAGE_REF, REPO_DIR
from .preflight import run_all_checks
from .system import get_version, human_size, is_installed, stream_cmd


# ── Copying output ─────────────────────────────────────────

# A copy is always mirrored to a file, so the text survives even when no
# clipboard is reachable — the usual reason to copy this is to paste it
# somewhere else for help.
EXPORT_NAME = "arinanolabs-last-output.txt"


def _to_clipboard(app, text: str) -> str | None:
    """Put `text` on a clipboard. Returns how it got there, or None.

    termux-clipboard-set reaches the real Android clipboard but needs the
    termux-api package and the Termux:API app. Textual's own path uses an
    OSC 52 escape, which only lands if the terminal honours it.
    """
    if shutil.which("termux-clipboard-set"):
        try:
            result = subprocess.run(
                ["termux-clipboard-set"], input=text, text=True, timeout=10
            )
            if result.returncode == 0:
                return "the Android clipboard"
        except (OSError, subprocess.SubprocessError):
            pass

    try:
        app.copy_to_clipboard(text)
        return "the terminal clipboard"
    except Exception:  # noqa: BLE001 - clipboard support is best effort
        return None


def _write_export(text: str) -> str | None:
    """Mirror the copy to a file, next to the repo when there is one.

    Deliberately does not create the repo directory: off-device there is no
    checkout, and a copy action has no business making one.
    """
    directory = REPO_DIR if os.path.isdir(REPO_DIR) else tempfile.gettempdir()
    path = os.path.join(directory, EXPORT_NAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path
    except OSError:
        return None


class CopyableScreen(Screen):
    """A screen whose visible output can be copied out as plain text.

    Subclasses return their content from `copy_payload`. The button is
    labelled "C" rather than a clipboard glyph: Termux's font cannot be
    relied on to have one.
    """

    BINDINGS = [("c", "copy", "Copy")]

    def copy_payload(self) -> str:
        raise NotImplementedError

    @on(Button.Pressed, "#copy")
    def _copy_pressed(self) -> None:
        self.action_copy()

    def action_copy(self) -> None:
        text = self.copy_payload().strip()
        if not text:
            self.notify("Nothing to copy yet.", severity="warning")
            return

        where = _to_clipboard(self.app, text)
        path = _write_export(text)

        if where and path:
            self.notify(f"Copied to {where}. Also saved to {path}")
        elif where:
            self.notify(f"Copied to {where}.")
        elif path:
            self.notify(f"No clipboard available — saved to {path}", severity="warning")
        else:
            self.notify("Could not copy or save the output.", severity="error")


# ── Confirmation ───────────────────────────────────────────


class ConfirmScreen(ModalScreen[bool]):
    """Modal yes/no. Destructive actions route through this."""

    BINDINGS = [("escape", "dismiss(False)", "Cancel")]

    def __init__(self, title: str, body: str, confirm_label: str = "Confirm") -> None:
        super().__init__()
        self._title = title
        self._body = body
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="dialog"):
            yield Label(self._title, id="dialog-title")
            yield Static(self._body, id="dialog-body")
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button(self._confirm_label, id="confirm", variant="error")

    @on(Button.Pressed, "#confirm")
    def _confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)


# ── Generic action runner ──────────────────────────────────


class ActionScreen(CopyableScreen):
    """Runs `runner(log)` in a thread and streams its output."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, title: str, runner, offer_restart: bool = False) -> None:
        super().__init__()
        self._title = title
        self._runner = runner
        self._offer_restart = offer_restart
        self._log: RichLog | None = None
        # RichLog keeps rendered strips, not text, so the plain lines are kept
        # alongside it for copying.
        self._lines: list[str] = []
        # Not _running: MessagePump uses that name for its own loop state, and
        # shadowing it stops the screen ever processing its mount.
        self._busy = True

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(self._title, classes="screen-title")
        yield RichLog(id="log", markup=True, wrap=True, auto_scroll=True)
        with Horizontal(id="action-buttons"):
            yield Button("C", id="copy")
            if self._offer_restart:
                yield Button("Restart", id="restart", variant="success", disabled=True)
            yield Button("Back", id="back", variant="primary", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self._log = self.query_one("#log", RichLog)
        self.query_one("#copy", Button).tooltip = "Copy this log"
        if self._offer_restart:
            self.query_one("#restart", Button).tooltip = "Relaunch alabs on the new code"
        self.run_task()

    def copy_payload(self) -> str:
        return "\n".join(self._lines)

    @work(thread=True)
    def run_task(self) -> None:
        def log(message: str = "") -> None:
            assert self._log is not None
            # Markup is for the pane; the copy should be readable as text.
            self._lines.append(Text.from_markup(message).plain)
            self.app.call_from_thread(self._log.write, message)

        try:
            self._runner(log)
        except Exception as e:  # noqa: BLE001 - the log pane is the error channel
            log(f"[bold red]Error:[/bold red] {e}")
        self.app.call_from_thread(self._finish)

    def _finish(self) -> None:
        self._busy = False
        button = self.query_one("#back", Button)
        button.disabled = False
        if self._offer_restart:
            restart = self.query_one("#restart", Button)
            restart.disabled = False
            restart.focus()
        else:
            button.focus()

    @on(Button.Pressed, "#restart")
    def _restart(self) -> None:
        if self._busy:
            self.notify("Still working — wait for it to finish.", severity="warning")
            return
        self.app.request_restart()

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        # The Back button is disabled while the worker runs, but the escape
        # binding calls this same action. Without the guard, escape walks out
        # of a screen the UI says you cannot leave — mid image pull, that
        # leaves a half-installed container with nothing on screen to say so.
        if self._busy:
            self.notify("Still working — this cannot be interrupted yet.", severity="warning")
            return
        self.app.pop_screen()


# ── Status ─────────────────────────────────────────────────


class StatusScreen(CopyableScreen):
    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Status", classes="screen-title")
        yield DataTable(id="status-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(id="action-buttons"):
            yield Button("C", id="copy")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[tuple[str, str, str]] = []

    def on_mount(self) -> None:
        table = self.query_one("#status-table", DataTable)
        table.add_columns("Check", "State", "Detail")
        self.query_one("#copy", Button).tooltip = "Copy this report"
        self.load_status()

    def copy_payload(self) -> str:
        marks = {"ok": "ok", "no": "--", "unknown": "??"}
        lines = [f"arinanoLabs status — {get_version()}", ""]
        lines += [
            f"{marks.get(state, '  '):<3} {name:<14} {detail}"
            for name, state, detail in self._rows
        ]
        return "\n".join(lines)

    @work(thread=True)
    def load_status(self) -> None:
        rows = [
            (
                check.name,
                "unknown" if check.unknown else ("ok" if check.ok else "no"),
                check.message,
            )
            for check in run_all_checks()
        ]
        running = desktop.is_running()
        rows.append(
            ("Desktop", "ok" if running else "no", "Running" if running else "Not running")
        )
        rows.append(("Image cache", "-", human_size(CACHE_DIR)))
        rows.append(("Version", "-", get_version()))
        self.app.call_from_thread(self._fill, rows)

    def _fill(self, rows: list[tuple[str, str, str]]) -> None:
        self._rows = rows
        table = self.query_one("#status-table", DataTable)
        for name, state, detail in rows:
            mark = {
                "ok": "[green]●[/green]",
                "no": "[red]○[/red]",
                "unknown": "[yellow]?[/yellow]",
            }.get(state, "[dim]·[/dim]")
            table.add_row(name, mark, detail)

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


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
    log(f"Pulling {IMAGE_REF} — this takes a few minutes...")
    rc = stream_cmd(
        f"proot-distro install {IMAGE_REF} --name {CONTAINER_NAME}", log, timeout=1800
    )

    log("")
    if rc == 0 and is_installed():
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
        "update": "Pull the latest arinanoLabs",
        "tools": "Extra tools (not implemented yet)",
        "status": "Environment checks and versions",
        "doctor": "Diagnose and repair the environment",
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
                yield Button("Tools", id="tools")
                yield Button("Status", id="status")
            with Grid(classes="row3"):
                yield Button("Doctor", id="doctor")
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
                    f"This downloads {IMAGE_REF} and takes a few minutes.",
                    confirm_label="Install",
                ),
                lambda ok: self.app.push_screen(ActionScreen("Install", run_reset)) if ok else None,
            )
            return
        self.app.push_screen(ActionScreen("Start Desktop", run_start))

    @on(Button.Pressed, "#stop")
    def _stop(self) -> None:
        self.app.push_screen(ActionScreen("Stop Desktop", run_stop))

    @on(Button.Pressed, "#update")
    def _update(self) -> None:
        self.app.push_screen(ActionScreen("Update", run_update, offer_restart=True))

    @on(Button.Pressed, "#tools")
    def _tools(self) -> None:
        self.app.push_screen(ToolsScreen())

    @on(Button.Pressed, "#status")
    def _status(self) -> None:
        self.app.push_screen(StatusScreen())

    @on(Button.Pressed, "#doctor")
    def _doctor(self) -> None:
        self.app.push_screen(DoctorScreen())

    @on(Button.Pressed, "#reset")
    def _reset(self) -> None:
        self.app.push_screen(
            ConfirmScreen(
                "Reset (Clean Install)",
                "This deletes the entire container and pulls a fresh image.\n\n"
                "Every file, setting, and package inside the container is lost "
                "permanently. Your Termux home is untouched.",
                confirm_label="Delete and reinstall",
            ),
            lambda ok: self.app.push_screen(ActionScreen("Reset", run_reset)) if ok else None,
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
            lambda ok: self.app.push_screen(ActionScreen("Clean Image Cache", run_clean_cache)) if ok else None,
        )


class DoctorScreen(CopyableScreen):
    """Environment diagnosis with a one-press repair for what is fixable."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._issues: list[doctor.Issue] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Doctor", classes="screen-title")
        yield DataTable(id="doctor-table", cursor_type="row", zebra_stripes=True)
        # Paired rows: these do not fit side by side on a phone terminal.
        with Grid(classes="row2"):
            yield Button("Re-scan", id="rescan")
            yield Button("Fix", id="fix", variant="success", disabled=True)
        with Grid(classes="row2"):
            yield Button("Diagnose", id="diagnose")
            yield Button("Dupes", id="dupes")
        with Horizontal(id="action-buttons"):
            yield Button("C", id="copy")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#doctor-table", DataTable).add_columns("Check", "State", "Detail")
        self.query_one("#copy", Button).tooltip = "Copy this report"

    def copy_payload(self) -> str:
        lines = [f"arinanoLabs doctor — {get_version()}", ""]
        for issue in self._issues:
            if issue.ok:
                mark = "ok "
            elif issue.unknown:
                mark = "?? "
            elif issue.fix is not None:
                mark = "FIX"
            else:
                mark = "-- "
            lines.append(f"{mark} {issue.name:<14} {issue.detail}")
        return "\n".join(lines)

    def on_screen_resume(self) -> None:
        """Also runs after returning from a fix, so the table is never stale."""
        self.scan()

    @work(thread=True)
    def scan(self) -> None:
        issues = doctor.diagnose()
        self.app.call_from_thread(self._show_issues, issues)

    def _show_issues(self, issues: list[doctor.Issue]) -> None:
        self._issues = issues
        table = self.query_one("#doctor-table", DataTable)
        table.clear()
        for issue in issues:
            if issue.ok:
                mark = "[green]●[/green]"
            elif issue.unknown:
                mark = "[yellow]?[/yellow]"
            elif issue.fix is not None:
                mark = "[yellow]○[/yellow]"
            else:
                mark = "[red]○[/red]"
            table.add_row(issue.name, mark, issue.detail)

        count = len(doctor.fixable(issues))
        button = self.query_one("#fix", Button)
        button.disabled = count == 0
        button.label = f"Fix ({count})" if count else "Fix"

    @on(Button.Pressed, "#rescan")
    def _rescan(self) -> None:
        self.scan()

    @on(Button.Pressed, "#diagnose")
    def _diagnose(self) -> None:
        """Same report the start sequence prints on failure, on demand."""
        self.app.push_screen(ActionScreen("Desktop Diagnostics", desktop.collect_diagnostics))

    @on(Button.Pressed, "#dupes")
    def _dupes(self) -> None:
        self.app.push_screen(DupesScreen())

    @on(Button.Pressed, "#fix")
    def _fix(self) -> None:
        issues = self._issues

        def runner(log) -> None:
            repaired, attempted = doctor.run_fixes(issues, log)
            if attempted:
                log(f"[bold]{repaired} of {attempted} repaired.[/bold]")
                if repaired < attempted:
                    log("Remaining problems need you — see the detail column.")

        self.app.push_screen(ActionScreen("Doctor — Fix", runner))

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


class DupesScreen(CopyableScreen):
    """Termux packages the container already provides.

    Removal is never folded into Doctor's Fix: uninstalling from Termux is
    the user's call about their own environment, not a repair.
    """

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._dupes: list[doctor.Duplicate] = []

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
        yield DataTable(id="dupes-table", cursor_type="row", zebra_stripes=True)
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
        self.app.call_from_thread(self._show, doctor.termux_duplicates())

    def _show(self, dupes: list[doctor.Duplicate]) -> None:
        self._dupes = dupes
        table = self.query_one("#dupes-table", DataTable)
        table.clear()
        for dupe in dupes:
            table.add_row(dupe.package, dupe.binary)

        button = self.query_one("#remove", Button)
        button.disabled = not dupes
        button.label = f"Remove ({len(dupes)})" if dupes else "Remove"

    def copy_payload(self) -> str:
        lines = [f"arinanoLabs Termux duplicates — {get_version()}", ""]
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
            if doctor.remove_termux_packages(packages, log):
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
            lambda ok: self.app.push_screen(ActionScreen("Remove duplicates", run)) if ok else None,
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


class ToolsScreen(CopyableScreen):
    """Search the container's package lists and install from them."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._results: list[packages.Package] = []
        # Kept alongside the widget: Static does not expose its text back.
        self.status_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Extra Tools", classes="screen-title")
        yield Input(placeholder="Search packages, e.g. neovim", id="query")
        yield Static("", id="tools-status")
        yield DataTable(id="tools-table", cursor_type="row", zebra_stripes=True)
        with Horizontal(id="action-buttons"):
            yield Button("C", id="copy")
            yield Button("Install", id="install", variant="success", disabled=True)
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#tools-table", DataTable).add_columns("", "Package", "Description")
        self.query_one("#copy", Button).tooltip = "Copy these results"
        self.query_one("#install", Button).tooltip = "Install the highlighted package"
        self.query_one("#query", Input).focus()
        self._status("Search for a package, then pick a row and press Install.")

    def _status(self, message: str) -> None:
        self.status_text = message
        self.query_one("#tools-status", Static).update(message)

    @on(Input.Submitted, "#query")
    def _submitted(self, event: Input.Submitted) -> None:
        term = event.value.strip()
        self._status(f"Searching for '{term}'...")
        self.run_search(term)

    @work(thread=True)
    def run_search(self, term: str) -> None:
        results, error = packages.search(term)
        self.app.call_from_thread(self._show, results, error)

    def _show(self, results: list[packages.Package], error: str | None) -> None:
        self._results = results
        table = self.query_one("#tools-table", DataTable)
        table.clear()

        for pkg in results:
            mark = "[green]I[/green]" if pkg.installed else ""
            table.add_row(mark, pkg.name, pkg.description[:70])

        button = self.query_one("#install", Button)
        button.disabled = not results

        if error:
            self._status(error)
        else:
            installed = sum(1 for p in results if p.installed)
            self._status(
                f"{len(results)} result(s), {installed} already installed "
                "(marked I). Highlight one and press Install."
            )

    def _selected(self) -> packages.Package | None:
        table = self.query_one("#tools-table", DataTable)
        if not self._results:
            return None
        row = table.cursor_row
        if row is None or not (0 <= row < len(self._results)):
            return None
        return self._results[row]

    @on(Button.Pressed, "#install")
    def _install(self) -> None:
        pkg = self._selected()
        if pkg is None:
            self._status("Highlight a row first.")
            return

        if pkg.installed:
            self._status(f"{pkg.name} is already installed.")
            return

        def run(log) -> None:
            if packages.install([pkg.name], log):
                log("")
                log(f"[green]{pkg.name} installed.[/green]")
            else:
                log("")
                log(f"[red]Could not install {pkg.name}.[/red]")

        self.app.push_screen(
            ConfirmScreen(
                f"Install {pkg.name}",
                f"{pkg.description}\n\n"
                "This installs into the container with apt. "
                "Termux is not touched.",
                confirm_label="Install",
            ),
            lambda ok: self.app.push_screen(ActionScreen(f"Install {pkg.name}", run)) if ok else None,
        )

    def copy_payload(self) -> str:
        lines = [f"arinanoLabs package search — {get_version()}", ""]
        if not self._results:
            lines.append("(no results)")
        lines += [
            f"{'I' if p.installed else ' '} {p.name:<28} {p.description}"
            for p in self._results
        ]
        return "\n".join(lines)

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


class ArinanoLabsApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "arinanoLabs"

    def __init__(self) -> None:
        super().__init__()
        self.restart_requested = False

    def on_mount(self) -> None:
        self.sub_title = get_version()
        self.push_screen(MainScreen())

    def request_restart(self) -> None:
        """Leave Textual first, then relaunch from main().

        Exiting before re-executing matters: it restores the terminal out of
        the alternate screen and raw mode. Replacing the process from inside a
        running app would leave the terminal wedged.
        """
        self.restart_requested = True
        self.exit()


def main() -> None:
    app = ArinanoLabsApp()
    app.run()

    if not app.restart_requested:
        return

    # execv, not another App().run(): the point of restarting is to load code
    # that git just changed, and the old modules are already imported.
    try:
        os.execv(sys.executable, [sys.executable, "-m", "installer.app"])
    except OSError as e:
        print(f"Could not restart automatically ({e}).")
        print("Run alabs again to pick up the update.")


if __name__ == "__main__":
    main()
