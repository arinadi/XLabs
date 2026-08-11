#!/usr/bin/env python3
"""arinanoLabs installer.

install.sh guarantees exactly two things: git and Python. Everything else is
here — Python libraries, the repo checkout, Termux packages, the Debian
container, and the alabs launcher.

This file is fetched and run on its own, before the repo exists on disk, so
it must not import from installer/ at module level. It runs unattended: it
reports problems and keeps going rather than prompting, because the usual
entry point is `curl ... | bash`, where stdin is not a terminal.
"""

import os
import shutil
import subprocess
import sys

REPO_URL = "https://github.com/arinadi/arinanoLabs.git"
REPO_DIR = os.path.expanduser("~/arinanoLabs")
BIN_DIR = os.path.expanduser("~/bin")
BASHRC = os.path.expanduser("~/.bashrc")

CONTAINER_NAME = "arinanolabs"
IMAGE_REF = "ghcr.io/arinadi/arinanolabs:latest"
ADMIN_USER = "admin"
PROOT_DIR = f"/data/data/com.termux/files/usr/var/lib/proot-distro/containers/{CONTAINER_NAME}"

CYAN, GREEN, YELLOW, RED, DIM, NC = (
    "\033[0;36m", "\033[0;32m", "\033[1;33m", "\033[0;31m", "\033[2m", "\033[0m",
)

_failures: list[str] = []


def say(msg: str) -> None:
    print(f"{CYAN}>>>{NC} {msg}")


def ok(msg: str) -> None:
    print(f"{GREEN}  ok{NC} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}  warning{NC} {msg}")


def fail(step: str, msg: str) -> None:
    print(f"{RED}  failed{NC} {msg}")
    _failures.append(step)


def run(cmd: str, timeout: int | None = None) -> int:
    """Run a shell command with its output going straight to the terminal."""
    try:
        return subprocess.run(cmd, shell=True, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        print(f"{RED}  timed out after {timeout}s{NC}")
        return 1


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


# ── Steps ──────────────────────────────────────────────────


def sync_repo() -> None:
    say("Fetching repository")
    if os.path.isdir(os.path.join(REPO_DIR, ".git")):
        if run(f"git -C {REPO_DIR} pull --ff-only") != 0:
            warn("fast-forward failed, resetting to origin/main")
            run(f"git -C {REPO_DIR} fetch origin main")
            if run(f"git -C {REPO_DIR} reset --hard origin/main") != 0:
                fail("repo", "could not update the repository")
                return
        ok(f"updated {REPO_DIR}")
    else:
        if run(f"git clone --depth 1 {REPO_URL} {REPO_DIR}") != 0:
            fail("repo", "clone failed")
            return
        ok(f"cloned to {REPO_DIR}")


def preflight() -> bool:
    """Report environment state. Returns False only on a fatal problem."""
    say("Checking environment")
    sys.path.insert(0, REPO_DIR)
    try:
        from installer.preflight import blocking_failure, run_all_checks
    except ImportError:
        warn("checks unavailable (repo not in place), continuing")
        return True

    checks = run_all_checks()
    width = max(len(c.name) for c in checks)
    for check in checks:
        mark = f"{GREEN}ok{NC}" if check.ok else f"{YELLOW}--{NC}"
        print(f"  {mark} {check.name.ljust(width)}  {DIM}{check.message}{NC}")

    blocker = blocking_failure(checks)
    if blocker:
        print(f"\n{RED}{blocker.name}: {blocker.message}{NC}")
        print("An internet connection is required to install.")
        return False
    return True


def install_libs() -> None:
    say("Installing Python libraries")
    req = os.path.join(REPO_DIR, "requirements.txt")
    target = f"-r {req}" if os.path.exists(req) else "textual"

    # Termux's Python is externally managed on newer releases, so the plain
    # install is tried first and the override only as a fallback.
    attempts = [
        f"{sys.executable} -m pip install {target} --quiet",
        f"{sys.executable} -m pip install {target} --quiet --break-system-packages",
        f"{sys.executable} -m pip install {target} --quiet --user",
    ]
    for cmd in attempts:
        if run(cmd) == 0:
            ok("textual installed")
            return
    fail("libs", "could not install textual")


def install_termux_packages() -> None:
    if not have("pkg"):
        warn("not a Termux environment, skipping Termux packages")
        return

    groups = {
        "proot-distro": ["proot-distro"],
        "Termux:X11": [
            "termux-x11-nightly", "x11-repo", "tur-repo",
            "xorg-xrandr", "netcat-openbsd",
        ],
        "audio": ["pulseaudio"],
        "graphics": [
            "mesa-zink", "vulkan-loader-android",
            "virglrenderer-android", "angle-android",
        ],
        "wake lock": ["termux-api"],
    }

    say("Updating Termux packages")
    if run("pkg update -y") != 0:
        warn("pkg update reported an error, continuing")

    for label, packages in groups.items():
        say(f"Installing {label}")
        if run(f"pkg install -y {' '.join(packages)}") == 0:
            ok(label)
        else:
            fail(label, f"pkg install failed for {label}")


def container_exists() -> bool:
    return os.path.isdir(os.path.join(PROOT_DIR, "rootfs"))


def install_container() -> None:
    say("Installing Debian container")
    if container_exists():
        ok("container already present, skipping")
        return

    if not have("proot-distro"):
        fail("container", "proot-distro is not available")
        return

    print(f"{DIM}  Pulling {IMAGE_REF} — this takes a few minutes.{NC}")
    if run(f"proot-distro install {IMAGE_REF} --name {CONTAINER_NAME}", timeout=1800) != 0:
        fail("container", "image pull failed")
        return

    if not container_exists():
        fail("container", "image pulled but no rootfs was created")
        return
    ok("container installed")


def setup_admin_user() -> None:
    """The image already ships an admin user; this repairs a container that
    was built or restored without one."""
    if not container_exists():
        return

    say("Verifying admin user")
    setup = (
        f"id {ADMIN_USER} >/dev/null 2>&1 || useradd -m -s /bin/bash {ADMIN_USER}; "
        f'echo "{ADMIN_USER}:{ADMIN_USER}" | chpasswd; '
        f'echo "{ADMIN_USER} ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/{ADMIN_USER}; '
        f"chmod 0440 /etc/sudoers.d/{ADMIN_USER}"
    )
    if run(f"proot-distro login {CONTAINER_NAME} -- bash -c '{setup}'", timeout=120) == 0:
        ok("admin user ready")
    else:
        fail("user", "could not configure the admin user")


def install_launcher() -> None:
    say("Installing launcher")
    source = os.path.join(REPO_DIR, "alabs")
    if not os.path.exists(source):
        fail("launcher", f"{source} not found")
        return

    os.chmod(source, 0o755)
    os.makedirs(BIN_DIR, exist_ok=True)
    link = os.path.join(BIN_DIR, "alabs")

    # ~/bin is on Termux's default PATH; symlink so `git pull` updates the
    # launcher too.
    if os.path.islink(link) or os.path.exists(link):
        os.remove(link)
    try:
        os.symlink(source, link)
    except OSError:
        shutil.copy2(source, link)
        os.chmod(link, 0o755)

    path_line = 'export PATH="$HOME/bin:$PATH"'
    try:
        existing = open(BASHRC).read() if os.path.exists(BASHRC) else ""
    except OSError:
        existing = ""
    if "$HOME/bin" not in existing:
        with open(BASHRC, "a") as f:
            f.write(f"\n# arinanoLabs\n{path_line}\n")

    ok(f"{link} -> {source}")


# ── Main ───────────────────────────────────────────────────


def main() -> int:
    print()
    print(f"{CYAN}===========================================")
    print(f"  arinanoLabs Installer")
    print(f"==========================================={NC}")
    print()

    sync_repo()

    if not preflight():
        return 1

    install_libs()
    install_termux_packages()
    install_container()
    setup_admin_user()
    install_launcher()

    print()
    if _failures:
        print(f"{YELLOW}Finished with problems in: {', '.join(sorted(set(_failures)))}{NC}")
        print("Fix those, then re-run the installer. It is safe to run again.")
        return 1

    print(f"{GREEN}Installation complete.{NC}")
    print()
    print("  Open a new terminal session, then run:  alabs")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
