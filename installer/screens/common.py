"""Shared screen infrastructure: copy-to-clipboard, the confirm dialog, and
the thread-worker runner every long menu action streams its output through.

Split out of app.py so a screen that only needs ActionScreen or
ConfirmScreen doesn't have to import (and read) every other screen to get
them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Callable

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, RichLog, Static

from ..const import REPO_DIR

# ── Copying output ─────────────────────────────────────────

# A copy is always mirrored to a file, so the text survives even when no
# clipboard is reachable — the usual reason to copy this is to paste it
# somewhere else for help.
EXPORT_NAME = "xlabs-last-output.txt"


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
    except Exception:
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


class ScrollableTable(DataTable):
    """A DataTable with Left/Right repurposed to horizontal scroll.

    Every table here uses cursor_type="row", which has no column cursor —
    DataTable's own Left/Right bindings call cursor_left/cursor_right, which
    are no-ops for a row cursor, so a wide column (a description, a URI) was
    unreachable with no working way to see the rest of it. Overriding the
    same keys wins: bindings merge by key across the MRO, most-derived last.
    """

    BINDINGS = [
        Binding("left", "scroll_left", "Scroll left", show=False),
        Binding("right", "scroll_right", "Scroll right", show=False),
    ]


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


def when_confirmed(app: App, build_screen: Callable[[], Screen]) -> Callable[[bool | None], None]:
    """push_screen callback that opens a screen only if the user confirmed.

    Written out rather than inlined as a lambda: the conditional-expression
    form discarded push_screen's return value, which mypy correctly objected
    to, and this reads better at five call sites.
    """

    def handler(confirmed: bool | None) -> None:
        if confirmed:
            app.push_screen(build_screen())

    return handler


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


class _Logger:
    """A callable log that also carries an in-place progress line.

    stream_cmd looks for a `.progress()` method to route carriage-return
    redraws to. Without it a download either shows nothing at all or fills
    the pane with thousands of near-identical lines.
    """

    def __init__(self, write, progress) -> None:
        self._write = write
        self._progress = progress

    def __call__(self, message: str = "") -> None:
        self._write(message)

    def progress(self, message: str) -> None:
        self._progress(message)


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
        yield Static("", id="progress")
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
            self.query_one("#restart", Button).tooltip = "Relaunch xlabs on the new code"
        self.run_task()

    def copy_payload(self) -> str:
        return "\n".join(self._lines)

    def _set_progress(self, message: str) -> None:
        self.query_one("#progress", Static).update(message)

    @work(thread=True)
    def run_task(self) -> None:
        def write(message: str = "") -> None:
            assert self._log is not None
            # Markup is for the pane; the copy should be readable as text.
            self._lines.append(Text.from_markup(message).plain)
            self.app.call_from_thread(self._log.write, message)

        def progress(message: str) -> None:
            self.app.call_from_thread(self._set_progress, message)

        log = _Logger(write, progress)

        try:
            self._runner(log)
        except Exception as e:
            log(f"[bold red]Error:[/bold red] {e}")
        self.app.call_from_thread(self._finish)

    def _finish(self) -> None:
        self._busy = False
        self._set_progress("")
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
        # Looked up by attribute, not isinstance(self.app, XLabsApp):
        # importing XLabsApp here would import installer.app, which imports
        # this module first to build every screen — a cycle. XLabsApp is the
        # only host that defines request_restart, so this is equivalent.
        request_restart = getattr(self.app, "request_restart", None)
        if callable(request_restart):
            request_restart()

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
