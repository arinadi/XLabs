"""npyscreen TUI for arinanoLabs."""

import npyscreen
import os


class MainMenuForm(npyscreen.FormWithMenus):
    """Main menu."""

    def create(self):
        from .ui import get_version
        self.name = f"📱 arinanoLabs v{get_version()}"

        self.menu = self.new_menu(name="Main Menu", footer="Press Enter to select")
        self.menu.addItem("Start Desktop", self.on_start, "1")
        self.menu.addItem("Stop Desktop", self.on_stop, "2")
        self.menu.addItem("Update", self.on_update, "3")
        self.menu.addItem("Extra Tools", self.on_tools, "4")
        self.menu.addItem("Status", self.on_status, "5")
        self.menu.addItem("Exit", self.on_exit, "0")

    def on_start(self):
        self.parentApp.switchForm("START")

    def on_stop(self):
        self.parentApp.switchForm("STOP")

    def on_update(self):
        self.parentApp.switchForm("UPDATE")

    def on_tools(self):
        self.parentApp.switchForm("TOOLS")

    def on_status(self):
        self.parentApp.switchForm("STATUS")

    def on_exit(self):
        self.parentApp.switchForm(None)


class OutputForm(npyscreen.Form):
    """Generic output form with Back button."""

    def create(self):
        self.output = self.add(
            npyscreen.MultiLineEdit,
            name="Output",
            value="",
            editable=False,
            max_height=15,
        )
        self.add(npyscreen.ButtonPress, name="Back", when_pressed_function=self.on_back)

    def set_output(self, text):
        self.output.value = text
        self.display()

    def on_back(self):
        self.parentApp.switchForm("MAIN")


class StartForm(OutputForm):
    def beforeEditing(self):
        self.name = "▶️  Start Desktop"
        self.set_output("Starting desktop...")

    def on_edit(self):
        from .start import start_desktop
        success = start_desktop()
        if success:
            self.set_output("✓ Desktop started!\n\nOpen Termux:X11 app to see your desktop.")
        else:
            self.set_output("✗ Failed to start desktop")


class StopForm(OutputForm):
    def beforeEditing(self):
        self.name = "⏹️  Stop Desktop"
        self.set_output("Stopping desktop...")

    def on_edit(self):
        from .start import stop_desktop
        stop_desktop()
        self.set_output("✓ Desktop stopped")


class UpdateForm(OutputForm):
    def beforeEditing(self):
        self.name = "🔄  Update"
        self.set_output("Pulling latest changes...")

    def on_edit(self):
        import subprocess
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if not os.path.exists(os.path.join(repo_dir, ".git")):
            self.set_output("✗ Not a git repository\nReinstall via install.sh")
            return

        result = subprocess.run(["git", "pull"], cwd=repo_dir, capture_output=True, text=True)

        if result.returncode != 0:
            subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_dir, capture_output=True)
            result = subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=repo_dir, capture_output=True, text=True)

        if result.returncode == 0:
            if "Already up to date" in result.stdout:
                self.set_output("✓ Already on latest version")
            else:
                self.set_output("✓ Updated!\n\nRestart alabs to use new version")
        else:
            self.set_output("✗ Update failed")


class ToolsForm(OutputForm):
    def beforeEditing(self):
        self.name = "🧰  Extra Tools"
        self.set_output(
            "  [1] Chromium Browser\n"
            "  [2] VS Code (code-server)\n"
            "  [3] Zsh + Oh My Zsh\n"
            "  [4] Neovim\n"
            "  [5] GitHub CLI\n\n"
            "  Coming soon!"
        )


class StatusForm(OutputForm):
    def beforeEditing(self):
        self.name = "📊  Status"
        from .start import is_running
        from .ui import is_installed, get_version
        from .gpu import detect_gpu, get_gpu_summary

        container = is_installed()
        running = is_running()
        gpu = detect_gpu()

        self.set_output(
            f"  Container:  {'✓ Installed' if container else '✗ Not found'}\n"
            f"  Desktop:    {'● Running' if running else '○ Not running'}\n"
            f"  GPU:        {get_gpu_summary(gpu)}\n"
            f"  Version:    {get_version()}\n"
        )


class ArinanoLabsApp(npyscreen.NPSApp):
    def main(self):
        self.addForm("MAIN", MainMenuForm, name="arinanoLabs")
        self.addForm("START", StartForm)
        self.addForm("STOP", StopForm)
        self.addForm("UPDATE", UpdateForm)
        self.addForm("TOOLS", ToolsForm)
        self.addForm("STATUS", StatusForm)
        self.switchForm("MAIN")


def run_npyscreen():
    app = ArinanoLabsApp()
    app.run()
