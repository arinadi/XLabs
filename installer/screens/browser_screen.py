"""Firefox/Chromium tuning for proot's ptrace overhead — see browser.py.

The safe tier has no downside and could live in Doctor's own Fix, but stays
here next to the reduced-security tier so both are one screen: a user
weighing the trade-off should see what "further" means without hunting for it.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid
from textual.widgets import Button, Footer, Header, Label, Static

from .. import browser
from ..system import get_version
from .common import ActionScreen, ConfirmScreen, CopyableScreen, when_confirmed


class BrowserScreen(CopyableScreen):
    """Firefox/Chromium tuning for proot's ptrace overhead — see browser.py.

    The safe tier has no downside and could live in Doctor's own Fix, but
    stays here next to the reduced-security tier so both are one screen: a
    user weighing the trade-off should see what "further" means without
    hunting for it.
    """

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._status_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Browser tuning", classes="screen-title")
        yield Static("", id="browser-status")
        with Grid(classes="row2"):
            yield Button("Tune Firefox", id="firefox-safe")
            yield Button("Tune Chromium", id="chromium-safe")
        yield Button("Reduce Firefox security further", id="firefox-reduced", variant="error")
        yield Button("Back", id="back", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#firefox-reduced", Button).tooltip = (
            "Disables Fission site isolation and Safe Browsing — read the confirmation first"
        )
        self._refresh()

    def on_screen_resume(self) -> None:
        """Also runs after returning from a tuning action, so status is
        never stale."""
        self._refresh()

    def _refresh(self) -> None:
        firefox = browser.firefox_present()
        chromium = browser.chromium_present()

        lines = [f"Firefox:  {'installed' if firefox else 'not installed'}"]
        if firefox:
            safe = browser.firefox_safe_tuning_ok()
            reduced = browser.firefox_reduced_security_ok()
            lines.append(f"  safe tuning:       {'applied' if safe else 'not applied'}")
            lines.append(f"  reduced security:  {'applied' if reduced else 'not applied'}")
        lines.append(f"Chromium: {'installed' if chromium else 'not installed'}")
        if chromium:
            chromium_ok = browser.chromium_tuning_ok()
            lines.append(f"  safe tuning:       {'applied' if chromium_ok else 'not applied'}")

        self._status_lines = lines
        self.query_one("#browser-status", Static).update("\n".join(lines))

        self.query_one("#firefox-safe", Button).disabled = not firefox
        self.query_one("#firefox-reduced", Button).disabled = not firefox
        self.query_one("#chromium-safe", Button).disabled = not chromium

    def copy_payload(self) -> str:
        return "\n".join([f"XLabs browser tuning — {get_version()}", "", *self._status_lines])

    @on(Button.Pressed, "#firefox-safe")
    def _firefox_safe(self) -> None:
        def run(log) -> None:
            if browser.apply_firefox_safe_tuning(log):
                log("")
                log("[green]Applied.[/green]")

        self.app.push_screen(ActionScreen("Tune Firefox", run))

    @on(Button.Pressed, "#chromium-safe")
    def _chromium_safe(self) -> None:
        def run(log) -> None:
            if browser.apply_chromium_tuning(log):
                log("")
                log("[green]Applied.[/green]")

        self.app.push_screen(ActionScreen("Tune Chromium", run))

    @on(Button.Pressed, "#firefox-reduced")
    def _firefox_reduced(self) -> None:
        def run(log) -> None:
            if browser.apply_firefox_reduced_security(log):
                log("")
                log("[green]Applied.[/green]")

        self.app.push_screen(
            ConfirmScreen(
                "Reduce Firefox security",
                "This disables Fission site isolation and Safe Browsing's "
                "phishing/malware warnings, in exchange for fewer content "
                "processes and less background I/O under proot.\n\n"
                "Fission loss means a compromised tab's content process can "
                "see others', not just its own. Safe Browsing loss means no "
                "warning before a known phishing or malware page loads.\n\n"
                "This project's own research recommends against applying "
                "this — only continue if you understand and accept the "
                "trade-off.",
                confirm_label="Apply anyway",
            ),
            when_confirmed(self.app, lambda: ActionScreen("Reduce Firefox security", run)),
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()
