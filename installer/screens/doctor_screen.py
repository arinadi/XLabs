"""Environment diagnosis with a one-press repair for what is fixable, plus
the on-demand diagnostics/tuning tools that don't belong in that repair list.
"""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

from .. import audio, bench, doctor, iobench
from .. import start as desktop
from ..const import CACHE_DIR
from ..system import get_version, human_size
from .browser_screen import BrowserScreen
from .common import ActionScreen, CopyableScreen, ScrollableTable
from .dupes_screen import DupesScreen


class DoctorScreen(CopyableScreen):
    """Environment diagnosis with a one-press repair for what is fixable."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._issues: list[doctor.Issue] = []
        self._info = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Doctor", classes="screen-title")
        yield Static("", id="doctor-info")
        yield ScrollableTable(id="doctor-table", cursor_type="row", zebra_stripes=True)
        with Grid(classes="row3"):
            yield Button("Re-scan", id="rescan")
            yield Button("Fix", id="fix", variant="success", disabled=True)
            yield Button("Tools", id="tools")
        with Grid(classes="row2"):
            yield Button("C", id="copy")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#doctor-table", DataTable).add_columns("Check", "State", "Detail")
        self.query_one("#copy", Button).tooltip = "Copy this report"
        self.query_one("#tools", Button).tooltip = "Dupes, Audio, GPU, IO, Browser tuning"

    def copy_payload(self) -> str:
        lines = [f"XLabs doctor — {get_version()}", self._info, ""]
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
        # Folded in from the old Status screen: not diagnosable problems,
        # just facts worth having on the same screen as everything else.
        info = (
            f"Desktop: {'running' if desktop.is_running() else 'stopped'}"
            f"  ·  Cache: {human_size(CACHE_DIR)}  ·  {get_version()}"
        )
        self.app.call_from_thread(self._show_issues, issues, info)

    def _show_issues(self, issues: list[doctor.Issue], info: str) -> None:
        # scan() runs in a background thread; by the time it calls back here
        # the user may already have navigated away (Back is one tap after
        # Tools resumes this screen and re-triggers a scan), popping this
        # screen off the stack before the callback arrives.
        if not self.is_mounted:
            return
        self._issues = issues
        self._info = info
        self.query_one("#doctor-info", Static).update(info)
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

    @on(Button.Pressed, "#tools")
    def _tools(self) -> None:
        self.app.push_screen(ToolsScreen())

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
    """On-demand diagnostics and tuning that don't belong in Doctor's own
    issue table — nothing here is "wrong" the way a failed Issue is; each is
    a scan, benchmark, or tuning pass the user runs when they want it, not
    something Doctor's Fix should ever do on its own.
    """

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Doctor Tools", classes="screen-title")
        with Grid(classes="row3"):
            yield Button("Dupes", id="dupes")
            yield Button("Audio", id="audio")
            yield Button("GPU", id="gpu")
        with Grid(classes="row3"):
            yield Button("IO", id="iobench")
            yield Button("Diagnose", id="diagnose")
            yield Button("Browser", id="browser")
        yield Button("Back", id="back", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#iobench", Button).tooltip = "Test which isolation preset is fastest"
        self.query_one("#diagnose", Button).tooltip = "Desktop session diagnostics, on demand"

    @on(Button.Pressed, "#dupes")
    def _dupes(self) -> None:
        self.app.push_screen(DupesScreen())

    @on(Button.Pressed, "#audio")
    def _audio(self) -> None:
        self.app.push_screen(ActionScreen("Audio Test", audio.test))

    @on(Button.Pressed, "#gpu")
    def _gpu(self) -> None:
        self.app.push_screen(ActionScreen("GPU Benchmark", bench.run))

    @on(Button.Pressed, "#iobench")
    def _iobench(self) -> None:
        self.app.push_screen(ActionScreen("IO Benchmark", iobench.run))

    @on(Button.Pressed, "#diagnose")
    def _diagnose(self) -> None:
        """Same report the start sequence prints on failure, on demand."""
        self.app.push_screen(ActionScreen("Desktop Diagnostics", desktop.collect_diagnostics))

    @on(Button.Pressed, "#browser")
    def _browser(self) -> None:
        self.app.push_screen(BrowserScreen())

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()
