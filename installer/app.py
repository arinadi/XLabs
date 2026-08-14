"""XLabs TUI entry point.

Textual app. Every menu entry runs its work in a thread worker and streams
output into a log pane, so the UI stays responsive while apt or proot-distro
takes minutes.

The screens themselves live under installer/screens/, one module per screen
(or small family of screens) — this file only wires MainScreen up as the
app's root and handles the restart-into-updated-code dance. Re-imports the
screen classes so `installer.app.SettingsScreen` etc. keep working for
anything (tests included) that imported them from here before the split.
"""

from __future__ import annotations

import os
import sys

from textual.app import App

from .screens.backup_screen import BackupScreen
from .screens.browser_screen import BrowserScreen
from .screens.claude_md_screen import ClaudeMdScreen
from .screens.common import (
    ActionScreen,
    ConfirmScreen,
    CopyableScreen,
    ScrollableTable,
    when_confirmed,
)
from .screens.doctor_screen import DoctorScreen, ToolsScreen
from .screens.dupes_screen import DupesScreen
from .screens.main_screen import MainScreen
from .screens.mcp_screen import AddMCPScreen, MCPScreen
from .screens.providers_screen import AddProviderScreen, ProvidersScreen
from .screens.settings_screen import SettingsScreen
from .screens.store_screen import AddRepoScreen, MirrorScreen, ReposScreen, StoreScreen
from .system import get_version

__all__ = [
    "ActionScreen",
    "AddMCPScreen",
    "AddProviderScreen",
    "AddRepoScreen",
    "BackupScreen",
    "BrowserScreen",
    "ClaudeMdScreen",
    "ConfirmScreen",
    "CopyableScreen",
    "DoctorScreen",
    "DupesScreen",
    "MCPScreen",
    "MainScreen",
    "MirrorScreen",
    "ProvidersScreen",
    "ReposScreen",
    "ScrollableTable",
    "SettingsScreen",
    "StoreScreen",
    "ToolsScreen",
    "XLabsApp",
    "when_confirmed",
]


class XLabsApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "XLabs"

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
    app = XLabsApp()
    app.run()

    if not app.restart_requested:
        return

    # execv, not another App().run(): the point of restarting is to load code
    # that git just changed, and the old modules are already imported.
    try:
        os.execv(sys.executable, [sys.executable, "-m", "installer.app"])
    except OSError as e:
        print(f"Could not restart automatically ({e}).")
        print("Run xlabs again to pick up the update.")


if __name__ == "__main__":
    main()
