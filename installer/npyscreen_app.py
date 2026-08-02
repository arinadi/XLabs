"""npyscreen TUI for arinanoLabs — lightweight, Termux-compatible."""

import npyscreen
import os
import sys


class MainMenuForm(npyscreen.Form):
    """Main menu with multi-select style buttons."""

    def beforeEditing(self):
        self.name = "📱 arinanoLabs"

    def create(self):
        from .ui import get_version
        version = get_version()

        self.add(npyscreen.MultiLineEdit, name="", value=f"  v{version}\n", editable=False, max_height=2)

        self.menu = self.add(
            npyscreen.MultiSelect,
            name="Menu",
            values=[
                "▶️  Start Desktop",
                "⏹️  Stop Desktop",
                "🔄  Update",
                "🧰  Extra Tools",
                "📊  Status",
                "🚪  Exit",
            ],
            value=[],
            scroll_exit=True,
        )

    def afterEditing(self):
        if not self.menu.value:
            return
        choice = self.menu.value[0]

        if choice == 0:  # Start
            self.parentApp.switchForm("START")
        elif choice == 1:  # Stop
            self.parentApp.switchForm("STOP")
        elif choice == 2:  # Update
            self.parentApp.switchForm("UPDATE")
        elif choice == 3:  # Tools
            self.parentApp.switchForm("TOOLS")
        elif choice == 4:  # Status
            self.parentApp.switchForm("STATUS")
        elif choice == 5:  # Exit
            self.parentApp.switchForm(None)


class StartForm(npyscreen.Form):
    def beforeEditing(self):
        self.name = "▶️  Start Desktop"

    def create(self):
        self.output = self.add(
            npyscreen.MultiLineEdit,
            name="Output",
            value="Starting desktop...\n",
            editable=False,
            max_height=15,
        )
        self.add(npyscreen.ButtonPress, name="Back", when_pressed_function=self.on_back)

    def on_edit(self):
        from .start import start_desktop
        success = start_desktop()
        if success:
            self.output.value = "✓ Desktop started!\nOpen Termux:X11 app"
        else:
            self.output.value = "✗ Failed to start desktop"
        self.display()

    def on_back(self):
        self.parentApp.switchForm("MAIN")


class StopForm(npyscreen.Form):
    def beforeEditing(self):
        self.name = "⏹️  Stop Desktop"

    def create(self):
        self.output = self.add(
            npyscreen.MultiLineEdit,
            name="Output",
            value="Stopping...\n",
            editable=False,
            max_height=15,
        )
        self.add(npyscreen.ButtonPress, name="Back", when_pressed_function=self.on_back)

    def on_edit(self):
        from .start import stop_desktop
        stop_desktop()
        self.output.value = "✓ Desktop stopped"
        self.display()

    def on_back(self):
        self.parentApp.switchForm("MAIN")


class UpdateForm(npyscreen.Form):
    def beforeEditing(self):
        self.name = "🔄  Update"

    def create(self):
        self.output = self.add(
            npyscreen.MultiLineEdit,
            name="Output",
            value="Pulling latest...\n",
            editable=False,
            max_height=15,
        )
        self.add(npyscreen.ButtonPress, name="Back", when_pressed_function=self.on_back)

    def on_edit(self):
        import subprocess
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if not os.path.exists(os.path.join(repo_dir, ".git")):
            self.output.value = "✗ Not a git repository"
            self.display()
            return

        result = subprocess.run(["git", "pull"], cwd=repo_dir, capture_output=True, text=True)

        if result.returncode != 0:
            subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_dir, capture_output=True)
            result = subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=repo_dir, capture_output=True, text=True)

        if result.returncode == 0:
            if "Already up to date" in result.stdout:
                self.output.value = "✓ Already on latest version"
            else:
                self.output.value = "✓ Updated!\nRestart alabs to use new version"
        else:
            self.output.value = "✗ Update failed"
        self.display()

    def on_back(self):
        self.parentApp.switchForm("MAIN")


class ToolsForm(npyscreen.Form):
    def beforeEditing(self):
        self.name = "🧰  Extra Tools"

    def create(self):
        self.tools = self.add(
            npyscreen.MultiSelect,
            name="Tools",
            values=[
                "Chromium Browser",
                "VS Code (code-server)",
                "Zsh + Oh My Zsh",
                "Neovim",
                "GitHub CLI",
            ],
            value=[],
            scroll_exit=True,
        )
        self.add(npyscreen.ButtonPress, name="Back", when_pressed_function=self.on_back)

    def on_back(self):
        self.parentApp.switchForm("MAIN")


class StatusForm(npyscreen.Form):
    def beforeEditing(self):
        self.name = "📊  Status"

    def create(self):
        from .start import is_running
        from .ui import is_installed, get_version
        from .gpu import detect_gpu, get_gpu_summary

        container = is_installed()
        running = is_running()
        gpu = detect_gpu()

        status = (
            f"  Container:  {'✓ Installed' if container else '✗ Not found'}\n"
            f"  Desktop:    {'● Running' if running else '○ Not running'}\n"
            f"  GPU:        {get_gpu_summary(gpu)}\n"
            f"  Version:    {get_version()}\n"
        )

        self.add(npyscreen.MultiLineEdit, name="", value=status, editable=False, max_height=8)
        self.add(npyscreen.ButtonPress, name="Back", when_pressed_function=self.on_back)

    def on_back(self):
        self.parentApp.switchForm("MAIN")


class ArinanoLabsApp(npyscreen.NPSApp):
    """Main Application."""

    def main(self):
        self.addForm("MAIN", MainMenuForm, name="arinanoLabs")
        self.addForm("START", StartForm, name="Start Desktop")
        self.addForm("STOP", StopForm, name="Stop Desktop")
        self.addForm("UPDATE", UpdateForm, name="Update")
        self.addForm("TOOLS", ToolsForm, name="Extra Tools")
        self.addForm("STATUS", StatusForm, name="Status")

        self.switchForm("MAIN")


def run_npyscreen():
    """Run the npyscreen TUI."""
    app = ArinanoLabsApp()
    app.run()
