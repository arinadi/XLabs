# Proposal: arinanoLabs v2.0 Update

> **Status:** Draft  
> **Date:** 2026-08-02  
> **Scope:** Full lifecycle management + UX overhaul

---

## 1. Overview

Transform arinanoLabs from a basic shell installer into a **professional-grade mobile Linux workstation** with:

- Python TUI for all operations
- GPU auto-configuration
- Self-healing infrastructure
- Real-time progress feedback

**Inspired by:** Termux_HackingLab_Setup (self-healing, version check) + termux-hacklab (GPU detect, progress UX)

---

## 2. The 6 Features

### Feature 1: GPU Auto-Detect + Config

**Problem:** Users don't know which GPU mode to use. Manual config is error-prone.

**Solution:**

```python
# Auto-detect via Android system props
ro.hardware.egl        → GPU vendor
ro.product.board       → GPU model
ro.hardware.chipname   → Chipset

# Generate config file
~/.config/gpu.conf:
  MESA_GL_VERSION_OVERRIDE=4.6
  MESA_GLES_VERSION_OVERRIDE=3.2
  GALLIUM_DRIVER=zink
  ZINK_DESCRIPTORS=lazy
```

**Detection Logic:**

| Signal | Driver | Config |
|--------|--------|--------|
| `qualcomm` in ro.hardware | Turnip + Zink | Vulkan → OpenGL |
| `mali` in ro.hardware | Panfrost | OpenGL direct |
| Unknown | llvmpipe | Software fallback |

**Integration:**
- Run during `arinanox install` and `arinanox start`
- Cache result in `~/.arinanolabs/gpu.conf`
- `arinanox status` shows current GPU mode

---

### Feature 2: Self-Update with Version Check

**Problem:** No way to know if update available. Manual `git pull` required.

**Solution:**

```python
# On every TUI launch
local_version = read("~/.arinanolabs/VERSION")        # e.g. "2.0.0"
remote_version = fetch("github.com/.../VERSION")       # e.g. "2.1.0"

if remote_version > local_version:
    show("Update available: 2.0.0 → 2.1.0")
    if confirm("Update now?"):
        git_pull()
        pip_install_requirements()
        restart()
```

**Files:**
- `VERSION` — semver string (e.g., "2.0.0")
- `CHANGELOG.md` — human-readable changes
- `installer/updater.py` — update logic

**Flow:**
```
Launch TUI → Check VERSION → Offer update → git pull → pip install → restart
```

---

### Feature 3: Self-Healing Mirror Fallback

**Problem:** Termux primary mirror often slow/down. Install fails silently.

**Solution:**

```python
MIRRORS = [
    "https://packages.termux.dev",           # Primary
    "https://mirror.mentality.rip/termux",   # Fallback 1
    "https://termux.mentality.rip",          # Fallback 2
]

def ensure_termux_mirror():
    for mirror in MIRRORS:
        try:
            run(f"pkg update -y", timeout=30)
            return  # Success
        except (TimeoutError, CalledProcessError):
            switch_mirror(mirror)
            continue
    
    error("All mirrors failed. Check internet connection.")
```

**When it runs:**
- Before `arinanox install`
- Before `arinanox update`
- When `pkg install` fails

---

### Feature 4: Internet Check Before Bootstrap

**Problem:** User runs installer, gets stuck at download with no error message.

**Solution:**

```python
def check_internet() -> bool:
    """TCP socket check to Google DNS."""
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except (OSError, socket.timeout):
        return False

def check_storage(min_gb=2) -> bool:
    """Ensure enough storage."""
    import shutil
    free_gb = shutil.disk_usage("/data").free / (1024**3)
    return free_gb >= min_gb
```

**Pre-flight check sequence:**
```
[1/5] Checking internet...        ✓
[2/5] Checking storage (2GB min)... ✓  
[3/5] Checking Python...          ✓
[4/5] Detecting GPU...            ✓ Adreno A660
[5/5] Checking proot-distro...    ✓ Debian 13
```

---

### Feature 5: Progress Spinner + Bar

**Problem:** Long operations (download, install) have no visual feedback.

**Solution:**

Using `rich` library:

```python
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.console import Console

console = Console()

with Progress(
    SpinnerColumn(),
    TextColumn("[bold blue]{task.description}"),
    BarColumn(),
    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    TimeRemainingColumn(),
) as progress:
    task = progress.add_task("Downloading image...", total=100)
    
    for chunk in response.iter_content(chunk_size=8192):
        file.write(chunk)
        progress.advance(task, len(chunk))
```

**Output:**
```
>>> Installing arinanoLabs...
⠹ Downloading Debian 13 image... ━━━━━━━━━━━━━━━━━━━ 62% · 1.2 MB/s · 0:00:23
```

**Components:**
- `ui.py` — shared spinner, progress bar, colored output
- Works in all operations (install, update, start)

---

### Feature 6: Interactive Tool Menu

**Problem:** Users want to install extra tools but don't know available options.

**Solution:**

```
╔═══════════════════════════════════════════╗
║  🧰 Extra Tools                          ║
╠═══════════════════════════════════════════╣
║                                           ║
║  [✓] 1. Chromium Browser                 ║
║  [✓] 2. VS Code (code-server)            ║
║  [ ] 3. Docker (rootless)                 ║
║  [ ] 4. Zsh + Oh My Zsh                  ║
║  [ ] 5. Neovim                            ║
║  [ ] 6. GitHub CLI (gh)                   ║
║                                           ║
║  [a] Install All  [n] None  [c] Continue  ║
║                                           ║
╚═══════════════════════════════════════════╝
```

**Tools catalog:**
```python
TOOLS = {
    "chromium": {
        "name": "Chromium Browser",
        "cmd": "apt-get install -y chromium-browser",
        "size": "150 MB",
    },
    "code": {
        "name": "VS Code (code-server)",
        "cmd": "curl -fsSL https://code-server.dev/install.sh | sh",
        "size": "200 MB",
    },
    "docker": {
        "name": "Docker (rootless)",
        "cmd": "curl -fsSL https://get.docker.com | sh",
        "size": "300 MB",
    },
    # ...
}
```

**Integration:**
- Option in main menu: `[5] 🧰 Install Extra Tools`
- Also available during Fresh Install
- Reuses existing `patch.sh` logic but with TUI

---

## 3. Python TUI Main Menu

```
╔═══════════════════════════════════════════╗
║        📱 arinanoLabs v2.0               ║
║        Debian 13 · MATE · Mobile          ║
╠═══════════════════════════════════════════╣
║                                           ║
║   [1] 📦 Fresh Install                    ║
║   [2] ▶️  Start Desktop                    ║
║   [3] ⏹️  Stop Desktop                     ║
║   [4] 🔄 Update                            ║
║   [5] 🧰 Install Extra Tools              ║
║   [6] 🧹 Clean Install (nuke + reinstall) ║
║   [7] 🗑️  Uninstall                        ║
║   [8] ⚙️  Settings                         ║
║   [9] 📊 System Status                     ║
║   [0] 🚪 Exit                              ║
║                                           ║
╚═══════════════════════════════════════════╝
```

---

## 4. Project Structure

```
arinanoLabs/
├── installer/
│   ├── __init__.py
│   ├── main.py              # Entry point + TUI menu
│   ├── install.py           # Fresh install + Clean install
│   ├── start.py             # Start desktop (PulseAudio → virgl → X11 → MATE)
│   ├── stop.py              # Stop desktop (kill all + cleanup)
│   ├── update.py            # Self-update mechanism
│   ├── uninstall.py         # Full uninstall
│   ├── status.py            # System status display
│   ├── settings.py          # User preferences
│   ├── gpu.py               # GPU detection + config generation
│   ├── preflight.py         # Internet, storage, deps checks
│   ├── mirror.py            # Self-healing mirror fallback
│   ├── tools.py             # Extra tools catalog + installer
│   └── ui.py                # Shared UI (spinner, progress, colors)
├── requirements.txt         # rich, requests
├── VERSION                  # "2.0.0"
├── CHANGELOG.md             # Release notes
├── bootstrap.sh             # Entry: install python + pip + launch TUI
└── scripts/                 # Legacy shell scripts (kept for CLI)
    ├── arinanox             # CLI wrapper
    └── ...
```

---

## 5. Implementation Plan

### Phase 1: Foundation (Week 1)

| Task | File | Effort | Depends |
|------|------|--------|---------|
| Project structure | `installer/` | 1h | — |
| UI components | `ui.py` | 3h | — |
| Pre-flight checks | `preflight.py` | 2h | — |
| Mirror fallback | `mirror.py` | 1h | — |
| Main menu TUI | `main.py` | 3h | ui.py |

**Deliverable:** TUI launches, shows menu, pre-flight works

### Phase 2: Lifecycle (Week 2)

| Task | File | Effort | Depends |
|------|------|--------|---------|
| GPU detection | `gpu.py` | 2h | — |
| Start desktop | `start.py` | 2h | gpu.py |
| Stop desktop | `stop.py` | 1h | — |
| System status | `status.py` | 2h | — |
| Fresh install | `install.py` | 4h | preflight, mirror, gpu |
| Clean install | `install.py` | 1h | install.py |

**Deliverable:** All core operations work via TUI

### Phase 3: Features (Week 3)

| Task | File | Effort | Depends |
|------|------|--------|---------|
| Extra tools menu | `tools.py` | 3h | — |
| Self-update | `update.py` | 2h | — |
| Uninstall | `uninstall.py` | 2h | — |
| Settings menu | `settings.py` | 2h | — |
| Bootstrap script | `bootstrap.sh` | 1h | — |

**Deliverable:** All 6 features implemented

### Phase 4: Polish (Week 4)

| Task | File | Effort | Depends |
|------|------|--------|---------|
| README update | README.md | 1h | — |
| Error handling | all | 2h | — |
| Testing on device | — | 4h | — |
| Bug fixes | — | 2h | — |

**Deliverable:** Production-ready v2.0

---

## 6. Dependencies

```txt
# requirements.txt
rich>=13.0        # TUI, progress bars, spinners
requests>=2.28    # HTTP for version check, downloads
```

**Bootstrap:**
```bash
# install.sh (run once)
pkg install python -y
pip install rich requests
python installer/main.py
```

---

## 7. Migration

### Before (v1.x)
```bash
curl bootstrap.sh | bash
arinanox start
arinanox stop
```

### After (v2.0)
```bash
# One-time setup
curl install.sh | bash

# Then use TUI
arinanolabs              # Launch TUI

# Or CLI (still works)
arinanolabs start
arinanolabs stop
```

**Backward compatible:** Shell scripts remain as CLI wrappers.

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Python not installed | `install.sh` installs python first |
| `rich` slow on old phones | Fallback to plain print if import fails |
| Network timeout | Retry logic + mirror fallback |
| Termux kills background | `termux-wake-lock` during operations |

---

## 9. Success Criteria

- [ ] Single command: `python main.py` launches TUI
- [ ] All 6 features work: GPU detect, self-update, mirror fallback, internet check, progress UX, tool menu
- [ ] 5 lifecycle operations: Install, Start, Stop, Uninstall, Clean Install
- [ ] Pre-flight catches issues before they cause failures
- [ ] Progress bar shows real-time speed + ETA
- [ ] Works on Android 7.0+ with 2GB+ RAM
- [ ] Total install < 5 minutes
