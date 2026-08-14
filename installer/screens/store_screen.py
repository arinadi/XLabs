"""Search the container's package lists and install from them, plus the
mirror picker and extra-repository management Store links out to.
"""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from .. import packages
from .common import ActionScreen, ConfirmScreen, ScrollableTable, when_confirmed


class StoreScreen(Screen):
    """Search the container's package lists and install from them.

    Space checks/unchecks the highlighted row for a batch install; Install
    then acts on every checked package. With nothing checked it falls back
    to installing just the highlighted row, so a single install still takes
    one press.
    """

    BINDINGS = [("escape", "back", "Back"), ("space", "toggle_check", "Check")]

    def __init__(self) -> None:
        super().__init__()
        self._results: list[packages.Package] = []
        self._checked: set[str] = set()
        # Kept alongside the widget: Static does not expose its text back.
        self.status_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Store", classes="screen-title")
        yield Input(placeholder="Search packages, e.g. neovim", id="query")
        yield Static("", id="store-status")
        yield ScrollableTable(id="store-table", cursor_type="row", zebra_stripes=True)
        with Grid(classes="row3"):
            yield Button("Mirror", id="mirror")
            yield Button("Repos", id="repos")
            yield Button("Installed", id="installed")
        with Grid(classes="row2"):
            yield Button("Install", id="install", variant="success", disabled=True)
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#store-table", DataTable).add_columns("", "Package", "Description")
        self.query_one("#install", Button).tooltip = (
            "Installs every checked package, or the highlighted one if none are checked"
        )
        self.query_one("#installed", Button).tooltip = "List everything installed"
        self.query_one("#query", Input).focus()
        self._status("Loading curated tools...")
        self.load_curated()

    def _status(self, message: str) -> None:
        self.status_text = message
        self.query_one("#store-status", Static).update(message)

    @on(Input.Submitted, "#query")
    def _submitted(self, event: Input.Submitted) -> None:
        term = event.value.strip()
        if not term:
            self._status("Loading curated tools...")
            self.load_curated()
            return
        self._status(f"Searching for '{term}'...")
        self.run_search(term)

    @on(Button.Pressed, "#installed")
    def _show_installed(self) -> None:
        self._status("Loading installed packages...")
        self.load_installed()

    @work(thread=True)
    def load_curated(self) -> None:
        results, error = packages.curated()
        self.app.call_from_thread(self._show, results, error, kind="curated")

    @work(thread=True)
    def load_installed(self) -> None:
        results, error = packages.installed()
        self.app.call_from_thread(self._show, results, error, kind="installed")

    @work(thread=True)
    def run_search(self, term: str) -> None:
        results, error = packages.search(term)
        self.app.call_from_thread(self._show, results, error)

    def _mark(self, pkg: packages.Package) -> str:
        if pkg.installed:
            return "[green]I[/green]"
        if pkg.name in self._checked:
            return "[green][x][/green]"
        return "[ ]"

    def _refill_table(self) -> None:
        """Redraws marks from the current results/checked set, without
        re-querying apt — used after a checkbox toggle.

        Restores the cursor row afterward: clear() resets it to the top,
        which would otherwise throw the highlight back to row 0 after every
        single checkbox toggle — exactly the row a user checking several in
        a row is about to press space on next.
        """
        table = self.query_one("#store-table", DataTable)
        row = table.cursor_row
        table.clear()
        for pkg in self._results:
            table.add_row(self._mark(pkg), pkg.name, pkg.description[:70])
        if row is not None and 0 <= row < len(self._results):
            table.move_cursor(row=row, animate=False, scroll=False)

    def _update_install_button(self) -> None:
        button = self.query_one("#install", Button)
        button.disabled = not self._results
        button.label = f"Install ({len(self._checked)})" if self._checked else "Install"

    def _show(
        self, results: list[packages.Package], error: str | None, kind: str = "search"
    ) -> None:
        self._results = results
        # A checked package not in the new results is kept — a second search
        # to add more picks to the same batch shouldn't lose the first ones.
        self._checked -= {p.name for p in results if p.installed}
        self._refill_table()
        self._update_install_button()

        if error:
            self._status(error)
            self.notify(error, title="Store", severity="error")
        elif kind == "curated":
            installed = sum(1 for p in results if p.installed)
            self._status(
                f"{len(results)} curated tool(s), {installed} already installed "
                "(marked I). Space checks a row for a batch install."
            )
        elif kind == "installed":
            self._status(f"{len(results)} package(s) installed in the container.")
        else:
            installed = sum(1 for p in results if p.installed)
            self._status(
                f"{len(results)} result(s), {installed} already installed "
                "(marked I). Space checks a row for a batch install."
            )

    def _selected(self) -> packages.Package | None:
        table = self.query_one("#store-table", DataTable)
        if not self._results:
            return None
        row = table.cursor_row
        if row is None or not (0 <= row < len(self._results)):
            return None
        return self._results[row]

    @on(DataTable.RowHighlighted, "#store-table")
    def _row_highlighted(self) -> None:
        # A table row is a thin touch target; naming the pick here — not
        # only inside the confirm dialog — catches a mistap before Install
        # is even pressed, not only before it runs.
        pkg = self._selected()
        if pkg is not None:
            state = "installed" if pkg.installed else "not installed"
            self._status(f"Highlighted: {pkg.name} ({state}) — space to check")

    def action_toggle_check(self) -> None:
        pkg = self._selected()
        if pkg is None:
            self.notify("Highlight a row first.", severity="warning")
            return
        if pkg.installed:
            self.notify(f"{pkg.name} is already installed.", severity="warning")
            return

        if pkg.name in self._checked:
            self._checked.discard(pkg.name)
        else:
            self._checked.add(pkg.name)
        self._refill_table()
        self._update_install_button()
        self._status(f"{len(self._checked)} package(s) checked to install.")

    @on(Button.Pressed, "#install")
    def _install(self) -> None:
        names = sorted(self._checked)
        if not names:
            pkg = self._selected()
            if pkg is None:
                self._status("Highlight a row first, or check some with space.")
                return
            if pkg.installed:
                self._status(f"{pkg.name} is already installed.")
                return
            names = [pkg.name]

        # Optimistic: the batch is now committed to this run, so the
        # checkboxes shouldn't still claim to be pending if the user comes
        # back here before it finishes.
        self._checked.clear()
        self._refill_table()
        self._update_install_button()

        label = names[0] if len(names) == 1 else f"{len(names)} packages"
        if len(names) == 1:
            pkg = next((p for p in self._results if p.name == names[0]), None)
            body = pkg.description if pkg else ""
        else:
            body = "\n".join(names)

        def run(log) -> None:
            if packages.install(names, log):
                log("")
                log(f"[green]{label} installed.[/green]")
            else:
                log("")
                log(f"[red]Could not install {label}.[/red]")

        self.app.push_screen(
            ConfirmScreen(
                f"Install {label}",
                f"{body}\n\n"
                "This installs into the container with apt. "
                "Termux is not touched.",
                confirm_label="Install",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Install {label}", run)),
        )

    @on(Button.Pressed, "#mirror")
    def _mirror(self) -> None:
        self.app.push_screen(MirrorScreen())

    @on(Button.Pressed, "#repos")
    def _repos(self) -> None:
        self.app.push_screen(ReposScreen())

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


class MirrorScreen(Screen):
    """Pick which Debian mirror the container fetches from.

    The list comes from Debian's own deb822 masterlist rather than being
    hardcoded, and candidates are measured by downloading from them. Latency
    ranking, which is what netselect-apt does, says little about throughput
    on mobile data.
    """

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._mirrors: list[tuple[str, str, str]] = list(packages.SEED_MIRRORS)
        self._speeds: dict[str, float | None] = {}
        # Kept alongside the widget: Static does not expose its text back.
        self.status_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Debian mirror", classes="screen-title")
        yield Static("", id="mirror-current")
        yield ScrollableTable(id="mirror-table", cursor_type="row", zebra_stripes=True)
        with Grid(classes="row3"):
            yield Button("Refresh", id="refresh")
            yield Button("Measure", id="measure")
            yield Button("Use", id="use", variant="success")
        yield Button("Back", id="back", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#mirror-table", DataTable).add_columns(
            "Mirror", "Where", "KB/s", "URI"
        )
        self._fill()
        self._refresh_current()

    def on_screen_resume(self) -> None:
        self._refresh_current()

    def _set_current(self, message: str) -> None:
        self.status_text = message
        self.query_one("#mirror-current", Static).update(message)

    def _refresh_current(self) -> None:
        current = packages.current_mirror()
        self._set_current(
            f"Currently: {current}" if current else "No sources file in the container"
        )

    def _fill(self) -> None:
        table = self.query_one("#mirror-table", DataTable)
        table.clear()
        for name, where, uri in self._mirrors:
            speed = self._speeds.get(uri)
            if speed is None:
                shown = "-" if uri not in self._speeds else "failed"
            else:
                shown = f"{speed:,.0f}"
            table.add_row(name, where, shown, uri)

    def _selected_mirror(self) -> tuple[str, str, str] | None:
        row = self.query_one("#mirror-table", DataTable).cursor_row
        if row is None or not (0 <= row < len(self._mirrors)):
            return None
        return self._mirrors[row]

    @on(DataTable.RowHighlighted, "#mirror-table")
    def _row_highlighted(self) -> None:
        # Reuses the "Currently" line rather than adding a row for this: on
        # a phone-height screen there is no free row to spare, and a table
        # row is thin enough to mistap, so naming the pick here — not only
        # inside the confirm dialog — catches that before Use is pressed.
        # on_screen_resume and every fetch/measure already restore this
        # line afterward, so nothing is permanently lost.
        mirror = self._selected_mirror()
        if mirror is not None:
            name, where, _uri = mirror
            self._set_current(f"Selected: {name} — {where}")

    @on(Button.Pressed, "#refresh")
    def _refresh(self) -> None:
        self._set_current("Fetching Debian's mirror list...")
        self.fetch()

    @work(thread=True)
    def fetch(self) -> None:
        mirrors = packages.fetch_mirrors()
        self.app.call_from_thread(self._took_list, mirrors)

    def _took_list(self, mirrors: list[tuple[str, str, str]]) -> None:
        self._mirrors = mirrors
        self._speeds = {}
        self._fill()
        self._refresh_current()

    @on(Button.Pressed, "#measure")
    def _measure(self) -> None:
        self._set_current(f"Measuring {len(self._mirrors)} mirrors, this takes a moment...")
        self.measure_all()

    @work(thread=True)
    def measure_all(self) -> None:
        for _name, _where, uri in list(self._mirrors):
            speed = packages.measure_mirror(uri)
            self.app.call_from_thread(self._took_speed, uri, speed)
        self.app.call_from_thread(self._sort_by_speed)

    def _took_speed(self, uri: str, speed: float | None) -> None:
        self._speeds[uri] = speed
        self._fill()

    def _sort_by_speed(self) -> None:
        self._mirrors.sort(key=lambda m: -(self._speeds.get(m[2]) or -1))
        self._fill()
        fastest = next(
            ((n, self._speeds[u]) for n, _, u in self._mirrors if self._speeds.get(u)),
            None,
        )
        self._set_current(
            f"Fastest: {fastest[0]} at {fastest[1]:,.0f} KB/s — highlight it and press Use"
            if fastest
            else "No mirror answered."
        )

    @on(Button.Pressed, "#use")
    def _use(self) -> None:
        mirror = self._selected_mirror()
        if mirror is None:
            self.notify("Highlight a mirror first.", severity="warning")
            return
        name, where, uri = mirror

        def run(log) -> None:
            packages.set_mirror(uri, log)

        self.app.push_screen(
            ConfirmScreen(
                f"Use {name}",
                f"{where}\n\n{uri}\n\n"
                "The container's sources are rewritten and the package lists "
                "refetched. Termux keeps its own mirror.",
                confirm_label="Switch",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Mirror: {name}", run)),
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


class ReposScreen(Screen):
    """Third-party apt repositories, added with their signing keys."""

    BINDINGS = [("escape", "back", "Back")]

    NOTE = (
        "Each is written with its own signing key under /etc/apt/keyrings, "
        "so apt verifies it the same way it verifies Debian."
    )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Extra repositories", classes="screen-title")
        yield Static(self.NOTE, id="repos-note")
        yield ScrollableTable(id="repos-table", cursor_type="row", zebra_stripes=True)
        with Grid(classes="row3"):
            yield Button("Add", id="add", variant="success")
            yield Button("Enable", id="enable")
            yield Button("Remove", id="remove", variant="error")
        with Grid(classes="row2"):
            yield Button("Re-scan", id="rescan")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def __init__(self) -> None:
        super().__init__()
        self._repos: list[packages.Repo] = []
        # Kept alongside the widget: Static does not expose its text back.
        self.status_text = self.NOTE

    def _note(self, message: str) -> None:
        self.status_text = message
        self.query_one("#repos-note", Static).update(message)

    def on_mount(self) -> None:
        self.query_one("#repos-table", DataTable).add_columns(
            "", "Repository", "What it gives you"
        )
        self._fill()

    def on_screen_resume(self) -> None:
        self._fill()

    def _fill(self) -> None:
        # Built-in repos first, then anything added by hand or in an earlier
        # session that this screen would otherwise have no record of.
        self._repos = list(packages.REPOS) + packages.discovered_custom_repos()
        table = self.query_one("#repos-table", DataTable)
        table.clear()
        for repo in self._repos:
            mark = "[green]on[/green]" if packages.repo_enabled(repo) else ""
            table.add_row(mark, repo.name, repo.description)
        # The list just changed shape, so any earlier highlight no longer
        # points at what it used to.
        self._note(self.NOTE)

    def _selected(self):
        row = self.query_one("#repos-table", DataTable).cursor_row
        if row is None or not (0 <= row < len(self._repos)):
            return None
        return self._repos[row]

    @on(DataTable.RowHighlighted, "#repos-table")
    def _row_highlighted(self) -> None:
        # Reuses the note line rather than adding a row for this: on a
        # phone-height screen there is no free row to spare, and a table
        # row is thin enough to mistap, so naming the pick here — not only
        # inside the confirm dialog — catches that before Enable/Remove is
        # even pressed.
        repo = self._selected()
        if repo is not None:
            state = "enabled" if packages.repo_enabled(repo) else "not enabled"
            self._note(f"Selected: {repo.name} ({state})")

    @on(Button.Pressed, "#add")
    def _add(self) -> None:
        self.app.push_screen(AddRepoScreen())

    @on(Button.Pressed, "#rescan")
    def _rescan(self) -> None:
        self._fill()

    @on(Button.Pressed, "#enable")
    def _enable(self) -> None:
        repo = self._selected()
        if repo is None:
            self.notify("Highlight a repository first.", severity="warning")
            return
        if packages.repo_enabled(repo):
            self.notify(f"{repo.name} is already enabled.", severity="warning")
            return

        def run(log) -> None:
            packages.add_repo(repo, log)

        if repo.key_url:
            provenance = f"\n\nIts signing key comes from:\n{repo.key_url}"
        else:
            provenance = "\n\nNo new key: this is the Debian archive you already trust."

        self.app.push_screen(
            ConfirmScreen(
                f"Enable {repo.name}",
                repo.description
                + provenance
                + "\n\nA repository you enable can install software on this system.",
                confirm_label="Enable",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Enable {repo.name}", run)),
        )

    @on(Button.Pressed, "#remove")
    def _remove(self) -> None:
        repo = self._selected()
        if repo is None:
            self.notify("Highlight a repository first.", severity="warning")
            return

        def run(log) -> None:
            packages.remove_repo(repo, log)

        self.app.push_screen(
            ConfirmScreen(
                f"Remove {repo.name}",
                "The repository and its key are deleted. Packages already "
                "installed from it stay, but stop receiving updates.",
                confirm_label="Remove",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Remove {repo.name}", run)),
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()


class AddRepoScreen(Screen):
    """A custom repository: name, URI, suites, components, signing key."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self.status_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Add repository", classes="screen-title")
        with VerticalScroll(id="add-repo-form"):
            yield Static(
                "A signing key is required — nothing here is added to apt's "
                "trusted set otherwise, and packages from it would fail to verify.",
                id="add-repo-note",
            )
            yield Label("Name (used as the filename)")
            yield Input(placeholder="e.g. syncthing", id="repo-name")
            yield Label("Repository URI")
            yield Input(placeholder="https://apt.syncthing.net/", id="repo-uri")
            yield Label("Suites")
            yield Input(placeholder="syncthing", id="repo-suites")
            yield Label("Components")
            yield Input(placeholder="release", value="main", id="repo-components")
            yield Label("Signing key URL")
            yield Input(placeholder="https://.../key.gpg", id="repo-key")
            yield Static("", id="add-repo-status")
        with Grid(classes="row2"):
            yield Button("Add", id="submit", variant="success")
            yield Button("Back", id="back", variant="primary")
        yield Footer()

    def _status(self, message: str) -> None:
        self.status_text = message
        self.query_one("#add-repo-status", Static).update(message)

    @on(Button.Pressed, "#submit")
    def _submit(self) -> None:
        name = self.query_one("#repo-name", Input).value.strip()
        uri = self.query_one("#repo-uri", Input).value.strip()
        suites = self.query_one("#repo-suites", Input).value.strip()
        components = self.query_one("#repo-components", Input).value.strip()
        key_url = self.query_one("#repo-key", Input).value.strip()

        problems = packages.validate_custom_repo(name, uri, suites, components, key_url)
        if problems:
            self._status("\n".join(f"- {p}" for p in problems))
            return

        repo = packages.build_custom_repo(name, uri, suites, components, key_url)

        def run(log) -> None:
            packages.add_repo(repo, log)

        self.app.push_screen(
            ConfirmScreen(
                f"Add {repo.name}",
                f"{uri}\nSuites: {suites}  Components: {components}\n\n"
                f"Signing key from:\n{key_url}\n\n"
                "A repository you add can install software on this system.",
                confirm_label="Add",
            ),
            when_confirmed(self.app, lambda: ActionScreen(f"Add {repo.name}", run)),
        )

    @on(Button.Pressed, "#back")
    def action_back(self) -> None:
        self.app.pop_screen()
