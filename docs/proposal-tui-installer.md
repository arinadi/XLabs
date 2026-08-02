# Proposal: Python TUI Installer for arinanoLabs

> **Status:** Draft  
> **Date:** 2026-08-02  
> **Author:** arinadi

---

## 1. Problem Statement

Current arinanoLabs setup flow:

```
curl bootstrap.sh | bash
```

**Issues:**
- No visual feedback during long operations
- No menu-driven interface for non-technical users
- `arinanox start/stop` is CLI-only, no TUI
- No self-update mechanism
- No pre-flight checks (internet, storage, GPU)
- Bootstrap is monolithic — fails = start over

---

## 2. Proposed Solution

Python-based TUI installer that runs **natively in Termux** (not proot). Single entry point for all lifecycle operations.

### Why Python?

| Criterion | Shell | Python |
|-----------|-------|--------|
| TUI libraries | Limited (dialog, fzf) | Rich (rich, textual, curses) |
| Cross-platform | POSIX only | Works everywhere |
| Error handling | Fragile | Robust try/except |
| Progress bars | Manual ASCII | `rich.progress` built-in |
| Maintainability | Hard at scale | Clean OOP structure |

Python is pre-installed in Termux (`pkg install python`). No bootstrap needed.

---

## 3. Features

### 3.1 Main Menu (TUI)

```
╔═══════════════════════════════════════════╗
║        📱 arinanoLabs Installer           ║
║           v2.0 · Debian 13 · MATE        ║
╠═══════════════════════════════════════════╣
║                                           ║
║   [1] 📦 Fresh Install                    ║
║   [2] ▶️  Start Desktop                    ║
║   [3] ⏹️  Stop Desktop                     ║
║   [4] 🔄 Update                            ║
║   [5] 🧹 Clean Install (nuke + reinstall) ║
║   [6] 🗑️  Uninstall                        ║
║   [7] ⚙️  Settings                         ║
║   [8] 📊 System Status                     ║
║   [9] ❓ Help                              ║
║   [0] 🚪 Exit                              ║
║                                           ║
╚═══════════════════════════════════════════╝
```

### 3.2 Lifecycle Operations

| Operation | Description |
|-----------|-------------|
| **Fresh Install** | Install proot, pull image, setup user, configure |
| **Start Desktop** | Launch PulseAudio → virgl → X11 → MATE |
| **Stop Desktop** | Kill all processes, cleanup temp files |
| **Update** | Check version → pull latest → re-apply user layer |
| **Clean Install** | Remove proot container completely → Fresh Install |
| **Uninstall** | Remove everything (proot, configs, Termux packages) |
| **Settings** | GPU mode, audio, display scaling |
| **System Status** | Show container size, running processes, GPU mode |

### 3.3 Pre-Flight Checks (before any operation)

```
[1/5] Checking internet...        ✓
[2/5] Checking storage (2GB min)... ✓
[3/5] Checking Termux packages...  ✓
[4/5] Detecting GPU...            ✓ Adreno A660 (Turnip)
[5/5] Checking proot-distro...    ✓ Debian 13 installed
```

### 3.4 GPU Auto-Detection + Config

```python
def detect_gpu() -> dict:
    """Detect GPU via Android system properties."""
    # Qualcomm Adreno → Turnip/Zink
    # Mali → Panfrost (if available)
    # Unknown → Software fallback
    
    return {
        "vendor": "qualcomm",
        "model": "Adreno A660",
        "driver": "turnip",
        "mesa_config": {
            "MESA_GL_VERSION_OVERRIDE": "4.6",
            "MESA_GLES_VERSION_OVERRIDE": "3.2",
            "GALLIUM_DRIVER": "zink",
            "ZINK_DESCRIPTORS": "lazy",
        }
    }
```

### 3.5 Self-Update Mechanism

```python
def check_update():
    """Compare local version with GitHub."""
    local = read_version("~/.arinanolabs/VERSION")
    remote = fetch("https://raw.githubusercontent.com/.../VERSION")
    
    if remote > local:
        print(f"Update available: {local} → {remote}")
        if confirm("Update now?"):
            pull_and_restart()
```

### 3.6 Self-Healing Mirror Fallback

```python
def ensure_termux_repo():
    """Auto-switch mirror if primary fails."""
    try:
        run("pkg update -y", timeout=30)
    except TimeoutError:
        print("Primary mirror slow, switching to fallback...")
        write("$PREFIX/etc/apt/sources.list", 
              "deb https://mirror.mentality.rip/termux/...")
        run("pkg update -y")
```

### 3.7 Progress UX

```
>>> Installing MATE desktop...
⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ Downloading packages (142/287)

[████████████░░░░░░░░] 62% · 1.2 MB/s · ETA 23s
```

Using `rich` library:
- Spinner animation
- Progress bar with speed + ETA
- Color-coded status (✓ green, ✗ red, ⚠ yellow)

---

## 4. Project Structure

```
arinanoLabs/
├── installer/
│   ├── __init__.py
│   ├── main.py              # Entry point + TUI menu
│   ├── install.py           # Fresh install logic
│   ├── start.py             # Start desktop
│   ├── stop.py              # Stop desktop
│   ├── update.py            # Self-update
│   ├── uninstall.py         # Full uninstall
│   ├── status.py            # System status display
│   ├── settings.py          # User preferences
│   ├── gpu.py               # GPU detection + config
│   ├── preflight.py         # Pre-flight checks
│   └── ui.py                # Shared UI components (spinner, progress, colors)
├── requirements.txt         # rich, requests
├── version                  # Version file
└── install.sh               # Bootstrap: pkg install python + pip install rich → python main.py
```

---

## 5. Implementation Plan

### Phase 1: Core TUI (Week 1)

| Task | File | Effort |
|------|------|--------|
| Setup project structure | `installer/` | 1h |
| Main menu TUI | `main.py` | 3h |
| Shared UI components | `ui.py` | 2h |
| Pre-flight checks | `preflight.py` | 2h |
| Start desktop | `start.py` | 2h |
| Stop desktop | `stop.py` | 1h |
| System status | `status.py` | 2h |

**Deliverable:** Working TUI with Start/Stop/Status

### Phase 2: Install/Uninstall (Week 2)

| Task | File | Effort |
|------|------|--------|
| Fresh install | `install.py` | 4h |
| Uninstall | `uninstall.py` | 2h |
| Clean install | `install.py` (nuke mode) | 1h |
| GPU detection | `gpu.py` | 2h |
| GPU config generation | `gpu.py` | 1h |

**Deliverable:** Full install/uninstall lifecycle

### Phase 3: Polish (Week 3)

| Task | File | Effort |
|------|------|--------|
| Self-update | `update.py` | 2h |
| Mirror fallback | `preflight.py` | 1h |
| Settings menu | `settings.py` | 2h |
| Bootstrap script | `install.sh` | 1h |
| README update | `README.md` | 1h |

**Deliverable:** Production-ready v2.0

---

## 6. Dependencies

```txt
# requirements.txt
rich>=13.0        # TUI components, progress bars, spinners
requests>=2.28    # HTTP for version check, downloads
```

**Install command:**
```bash
pkg install python -y
pip install rich requests
python main.py
```

---

## 7. Migration Path

### Current (v1.x)
```bash
curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/bootstrap.sh | bash
# → Downloads shell scripts, runs setup
```

### New (v2.0)
```bash
# One-time bootstrap
pkg install python -y && pip install rich requests
git clone https://github.com/arinadi/arinanoLabs.git
python arinanoLabs/installer/main.py

# Or via short URL (bootstrap.sh installs python + launches TUI)
curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.sh | bash
```

### Backward Compatibility
- `arinanox start/stop/status` CLI commands remain (wrapper scripts)
- `bootstrap.sh` updated to launch TUI or run non-interactive install
- User manifest (`user-manifest.yaml`) format unchanged

---

## 8. UI Mockups

### Install Progress
```
╔═══════════════════════════════════════════╗
║  📦 Installing arinanoLabs               ║
╠═══════════════════════════════════════════╣
║                                           ║
║  [✓] System packages updated              ║
║  [✓] Termux:X11 installed                 ║
║  [✓] proot-distro installed               ║
║  [▼] Debian 13 image downloading...       ║
║                                           ║
║  [████████████░░░░░░░░] 62% · 1.2 MB/s   ║
║                                           ║
╚═══════════════════════════════════════════╝
```

### System Status
```
╔═══════════════════════════════════════════╗
║  📊 arinanoLabs Status                   ║
╠═══════════════════════════════════════════╣
║                                           ║
║  Container:  ✓ arinanox (580 MB)          ║
║  Desktop:    ● MATE running               ║
║  GPU:        ✓ Turnip (Adreno A660)       ║
║  Audio:      ✓ PulseAudio (port 4713)     ║
║  Storage:    12.3 GB free                 ║
║  Version:    2.0.0 (latest)               ║
║                                           ║
╚═══════════════════════════════════════════╝
```

### GPU Detection
```
╔═══════════════════════════════════════════╗
║  🎮 GPU Detection                        ║
╠═══════════════════════════════════════════╣
║                                           ║
║  Vendor:    Qualcomm                      ║
║  GPU:       Adreno A660                   ║
║  Driver:    Turnip (Vulkan)               ║
║  Renderer:  Zink (OpenGL on Vulkan)       ║
║  Mode:      Hardware accelerated          ║
║                                           ║
║  Config written to: ~/.config/gpu.conf    ║
║                                           ║
╚═══════════════════════════════════════════╝
```

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Python not installed | Can't run TUI | `install.sh` bootstrap installs python first |
| `rich` library slow on old phones | Laggy UI | Use `rich` sparingly, fallback to plain print |
| Termux kills background process | Install中断 | Use `termux-wake-lock` during operations |
| Network timeout during image pull | Partial install | Checksum verification + resume support |

---

## 10. Success Criteria

- [ ] Single command to launch TUI: `python main.py`
- [ ] All 5 operations work: Install, Start, Stop, Uninstall, Clean Install
- [ ] GPU auto-detected correctly on Qualcomm/Mali devices
- [ ] Progress bar shows real-time download speed + ETA
- [ ] Self-update checks GitHub on launch
- [ ] Pre-flight catches missing deps before install
- [ ] Total install time < 5 minutes on decent connection
- [ ] Works on Android 7.0+ with 2GB+ RAM
