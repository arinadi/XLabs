"""arinanoLabs TUI.

Textual app. Every menu entry runs its work in a thread worker and streams
output into a log pane, so the UI stays responsive while apt or proot-distro
takes minutes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    RichLog,
    Static,
)

from . import doctor
from . import start as desktop
from .const import CACHE_DIR, CONTAINER_NAME, IMAGE_REF, REPO_DIR
from .preflight import run_all_checks
from .system import get_version, human_size, is_installed, run_cmd, stream_cmd


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

    def __init__(self, title: str, runner) -> None:
        super().__init__()
        self._title = title
        self._runner = runner
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
            yield Button("Back", id="back", variant="primary", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self._log = self.query_one("#log", RichLog)
        self.query_one("#copy", Button).tooltip = "Copy this log"
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
        button.focus()

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
        log("[green]Up to date.[/green] Restart alabs to pick up changes.")
    else:
        log("[red]Update failed.[/red]")


def run_reset(log) -> None:
    if desktop.is_running():
        log("Stopping desktop...")
        desktop.stop_desktop(log)
        log("")

    # Scoped to this container: a bare 'proot' pattern also kills unrelated
    # proot-distro sessions the user may have running.
    log("Killing leftover proot processes for this container...")
    run_cmd(f"pkill -9 -f 'proot.*{CONTAINER_NAME}' 2>/dev/null")

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

    if desktop.is_running():
        log("Stopping desktop first...")
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

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="menu"):
            yield Button("Start Desktop", id="start", variant="success")
            yield Button("Stop Desktop", id="stop", variant="warning")
            yield Button("Update", id="update")
            yield Button("Extra Tools", id="tools")
            yield Button("Status", id="status")
            yield Button("Doctor", id="doctor")
            yield Button("Reset (Clean Install)", id="reset", variant="error")
            yield Button("Clean Image Cache", id="cache")
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
        self.app.push_screen(ActionScreen("Update", run_update))

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
        # Two rows: five buttons side by side do not fit a phone terminal.
        with Horizontal(id="doctor-buttons"):
            yield Button("Re-scan", id="rescan")
            yield Button("Fix", id="fix", variant="success", disabled=True)
            yield Button("Diagnose", id="diagnose")
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


class ToolsScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Extra Tools", classes="screen-title")
        yield Static(
            "Not implemented yet.\n\n"
            "Chromium, code-server, Neovim and GitHub CLI are planned. Until "
            "they land, install them inside the container:\n\n"
            f"    proot-distro login {CONTAINER_NAME} -- apt install <package>",
            id="tools-body",
        )
        yield Button("Back", id="back", variant="primary")
        yield Footer()

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


class ArinanoLabsApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "arinanoLabs"

    def on_mount(self) -> None:
        self.sub_title = get_version()
        self.push_screen(MainScreen())


def main() -> None:
    ArinanoLabsApp().run()


if __name__ == "__main__":
    main()
