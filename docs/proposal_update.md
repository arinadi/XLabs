# Proposal: arinanoLabs v2.0 Update

> **Status:** Draft  
> **Date:** 2026-08-02  
> **Scope:** Python TUI installer + 6 features

---

## 1. Overview

Transform arinanoLabs from shell-only installer into a **Python TUI-driven mobile Linux workstation** with professional UX.

**Entry point:**
```bash
curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.py | python
```

---

## 2. Install Flow

### 2.1 User Journey

```
User runs curl command
    ↓
Python script downloads
    ↓
TUI Welcome screen appears
    ↓
[Install] button clicked
    ↓
Pre-flight checks (internet, storage, GPU)
    ↓
Installing... (progress bar)
    ↓
Done! Instructions shown
```

### 2.2 Welcome TUI

```
╔═══════════════════════════════════════════════╗
║                                               ║
║          📱 arinanoLabs v2.0                  ║
║     Your phone is a Linux workstation         ║
║                                               ║
╠═══════════════════════════════════════════════╣
║                                               ║
║  Debian 13 · MATE · Firefox ESR · Dev tools   ║
║                                               ║
║  ✓ No root required                           ║
║  ✓ ~30 seconds install                        ║
║  ✓ GPU accelerated                            ║
║                                               ║
╠═══════════════════════════════════════════════╣
║                                               ║
║         [ ▶️  Install arinanoLabs ]            ║
║                                               ║
╚═══════════════════════════════════════════════╝
```

### 2.3 Already Installed Detection

```python
PROOT_DIR = "/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanox"

if os.path.exists(PROOT_DIR):
    # Show different screen
    ╔═══════════════════════════════════════════════╗
    ║  📱 arinanoLabs v2.0                  ✓      ║
    ╠═══════════════════════════════════════════════╣
    ║                                               ║
    ║   [1] ▶️  Start Desktop                       ║
    ║   [2] 🔄 Update                               ║
    ║   [3] 🧹 Clean Reinstall                      ║
    ║   [4] 🗑️  Uninstall                            ║
    ║   [5] 📊 Status                                ║
    ║                                               ║
    ║   [0] 🚪 Exit                                  ║
    ║                                               ║
    ╚═══════════════════════════════════════════════╝
```

### 2.4 Installing Progress

```
╔═══════════════════════════════════════════════╗
║  📦 Installing arinanoLabs                    ║
╠═══════════════════════════════════════════════╣
║                                               ║
║  [✓] System packages updated                  ║
║  [✓] Termux:X11 installed                     ║
║  [✓] proot-distro installed                   ║
║  [▼] Debian 13 image downloading...           ║
║                                               ║
║  [████████████░░░░░░░░] 62% · 1.2 MB/s       ║
║                                               ║
╚═══════════════════════════════════════════════╝
```

---

## 3. Post-Install: TUI via `alabs`

After install, user runs single command → TUI appears.

```bash
alabs                  # Launch TUI
```

### Main Menu TUI

```
╔═══════════════════════════════════════════════╗
║          📱 arinanoLabs v2.0                  ║
║     Debian 13 · MATE · Ready                 ║
╠═══════════════════════════════════════════════╣
║                                               ║
║   [1] ▶️  Start Desktop                       ║
║   [2] ⏹️  Stop Desktop                        ║
║   [3] 🔄 Update                               ║
║   [4] 🧰 Extra Tools                          ║
║   [5] 📊 Status                                ║
║   [6] 🗑️  Uninstall                            ║
║                                               ║
║   [0] 🚪 Exit                                  ║
║                                               ║
╚═══════════════════════════════════════════════╝
```

### Status Screen (option 5)

```
╔═══════════════════════════════════════════════╗
║  📊 arinanoLabs Status                       ║
╠═══════════════════════════════════════════════╣
║                                               ║
║  Container:  ✓ arinanox (580 MB)              ║
║  Desktop:    ● MATE running                   ║
║  GPU:        ✓ Turnip (Adreno A660)           ║
║  Audio:      ✓ PulseAudio                     ║
║  Version:    2.0.0 (latest)                   ║
║                                               ║
║         [ Press any key to return ]            ║
║                                               ║
╚═══════════════════════════════════════════════╝
```

### Extra Tools (option 4)

```
╔═══════════════════════════════════════════════╗
║  🧰 Extra Tools                              ║
╠═══════════════════════════════════════════════╣
║                                               ║
║  [✓] 1. Chromium Browser                     ║
║  [✓] 2. VS Code (code-server)                ║
║  [ ] 3. Zsh + Oh My Zsh                      ║
║  [ ] 4. Docker (rootless)                     ║
║  [ ] 5. Neovim                                ║
║                                               ║
║         [ Install Selected ]                  ║
║                                               ║
╚═══════════════════════════════════════════════╝
```

---

## 4. The 6 Features

### Feature 1: GPU Auto-Detect + Config

```python
def detect_gpu():
    """Auto-detect GPU via Android props."""
    egl = subprocess.getoutput("getprop ro.hardware.egl")
    
    if "qualcomm" in egl.lower():
        return {"vendor": "qualcomm", "driver": "turnip"}
    elif "mali" in egl.lower():
        return {"vendor": "arm", "driver": "panfrost"}
    else:
        return {"vendor": "unknown", "driver": "software"}

def write_gpu_config(gpu):
    """Write Mesa config for detected GPU."""
    config = {
        "turnip": {
            "GALLIUM_DRIVER": "zink",
            "MESA_GL_VERSION_OVERRIDE": "4.6",
            "ZINK_DESCRIPTORS": "lazy",
        },
        "panfrost": {
            "GALLIUM_DRIVER": "panfrost",
        },
        "software": {
            "LIBGL_ALWAYS_SOFTWARE": "1",
        }
    }
    # Write to ~/.config/gpu.conf
```

### Feature 2: Self-Update with Version Check

```python
def check_update():
    """Check GitHub for newer version."""
    VERSION_FILE = "~/.arinanolabs/VERSION"
    REMOTE_URL = "https://raw.githubusercontent.com/arinadi/arinanoLabs/main/VERSION"
    
    local = open(VERSION_FILE).read().strip()
    remote = requests.get(REMOTE_URL).text.strip()
    
    if remote > local:
        return {"available": True, "from": local, "to": remote}
    return {"available": False}
```

### Feature 3: Self-Healing Mirror Fallback

```python
MIRRORS = [
    "https://packages.termux.dev",
    "https://mirror.mentality.rip/termux",
]

def ensure_mirror():
    """Try mirrors until one works."""
    for mirror in MIRRORS:
        try:
            run(f"pkg update -y", timeout=30)
            return
        except:
            write_sources_list(mirror)
    error("All mirrors failed")
```

### Feature 4: Internet + Storage Check

```python
def preflight():
    """Run all checks before install."""
    checks = [
        ("Internet", check_internet),
        ("Storage (2GB min)", check_storage),
        ("Python", check_python),
        ("GPU", detect_gpu),
    ]
    for name, fn in checks:
        result = fn()
        status = "✓" if result else "✗"
        print(f"  [{status}] {name}")
```

### Feature 5: Progress UX

```python
from rich.progress import Progress, BarColumn, TextColumn

with Progress() as progress:
    task = progress.add_task("Downloading...", total=100)
    for chunk in response.iter_content(8192):
        file.write(chunk)
        progress.advance(task, len(chunk))
```

### Feature 6: Extra Tools Menu

```
╔═══════════════════════════════════════════╗
║  🧰 Extra Tools                          ║
╠═══════════════════════════════════════════╣
║  [✓] 1. Chromium Browser                 ║
║  [✓] 2. VS Code (code-server)            ║
║  [ ] 3. Zsh + Oh My Zsh                  ║
║  [ ] 4. Docker (rootless)                 ║
║                                           ║
║         [ Install Selected ]              ║
╚═══════════════════════════════════════════╝
```

---

## 5. Project Structure

```
arinanoLabs/
├── install.py               # Entry point (curl | python)
├── alabs                    # Post-install TUI launcher (installed to PATH)
├── installer/
│   ├── __init__.py
│   ├── welcome.py           # Welcome/already-installed screen
│   ├── menu.py              # Main menu TUI (post-install)
│   ├── install.py           # Install logic + progress
│   ├── start.py             # Start desktop
│   ├── stop.py              # Stop desktop
│   ├── update.py            # Self-update
│   ├── uninstall.py         # Uninstall
│   ├── status.py            # Status screen
│   ├── tools.py             # Extra tools menu
│   ├── gpu.py               # GPU detection
│   ├── preflight.py         # Pre-flight checks
│   ├── mirror.py            # Mirror fallback
│   └── ui.py                # Shared UI components
├── VERSION                  # "2.0.0"
├── requirements.txt         # rich, requests
└── scripts/                 # Legacy CLI wrappers
    └── arinanox             # Bash CLI (backward compat)
```

---

## 6. Implementation Plan

### Phase 1: Core TUI (Week 1)

| Task | File | Effort |
|------|------|--------|
| Entry point | `install.py` | 1h |
| Welcome screen | `installer/welcome.py` | 2h |
| UI components | `installer/ui.py` | 2h |
| Pre-flight checks | `installer/preflight.py` | 2h |
| Mirror fallback | `installer/mirror.py` | 1h |

**Deliverable:** `curl | python` shows welcome, detects install status

### Phase 2: Install + Lifecycle (Week 2)

| Task | File | Effort |
|------|------|--------|
| Install logic | `installer/install.py` | 4h |
| Start desktop | `installer/start.py` | 2h |
| Stop desktop | `installer/stop.py` | 1h |
| GPU detection | `installer/gpu.py` | 2h |

**Deliverable:** Full install + start/stop via TUI

### Phase 3: Features (Week 3)

| Task | File | Effort |
|------|------|--------|
| Extra tools menu | `installer/tools.py` | 3h |
| Self-update | `installer/update.py` | 2h |
| Uninstall | `installer/uninstall.py` | 2h |
| Health check | `installer/doctor.py` | 2h |

**Deliverable:** All 6 features working

### Phase 4: Polish (Week 4)

| Task | File | Effort |
|------|------|--------|
| CLI wrapper | `scripts/arinanox` | 1h |
| README update | README.md | 1h |
| Testing | — | 4h |

**Deliverable:** Production-ready v2.0

---

## 7. Dependencies

```txt
# requirements.txt
rich>=13.0
requests>=2.28
```

---

## 8. Migration

### v1.x (current)
```bash
curl bootstrap.sh | bash    # Shell scripts
arinanox start               # CLI
```

### v2.0 (proposed)
```bash
# Install (one-time)
curl install.py | python

# Daily use
alabs                        # Launch TUI
```

**Commands:**
| Command | Interface | Description |
|---------|-----------|-------------|
| `curl \| python` | TUI | First-time install |
| `alabs` | TUI | Post-install menu |
| `arinanox` | CLI | Backward compat wrapper |

---

## 9. Success Criteria

- [ ] `curl | python` launches Welcome TUI
- [ ] `alabs` launches Main Menu TUI
- [ ] Detects already-installed via proot-distro dir
- [ ] Pre-flight checks run before install
- [ ] GPU auto-detected
- [ ] Progress bar with speed + ETA
- [ ] Self-update checks GitHub
- [ ] All 6 features working
- [ ] Works on Android 7.0+, 2GB+ RAM
