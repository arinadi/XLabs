<div align="center">
  <h1>📱 arinanoLabs</h1>
  <p><strong>Your phone is a Linux workstation — ~30s to a working desktop, not 30 minutes of apt.</strong></p>
  <p>
    <a href="https://github.com/arinadi/arinanoLabs/actions"><img src="https://img.shields.io/github/actions/workflow/status/arinadi/arinanoLabs/build-image.yml?label=build"></a>
    <a href="https://github.com/arinadi/arinanoLabs/blob/main/LICENSE"><img src="https://img.shields.io/github/license/arinadi/arinanoLabs"></a>
    <a href="https://github.com/arinadi/arinanoLabs/releases"><img src="https://img.shields.io/github/v/release/arinadi/arinanoLabs"></a>
  </p>

  ```bash
  curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.sh | bash
  ```

  <img src="docs/arinanox-screenshot.jpg" alt="arinanoLabs desktop" width="360" style="border-radius:12px;">
  <p>
    Debian 13 &nbsp;·&nbsp; MATE &nbsp;·&nbsp; Firefox ESR &nbsp;·&nbsp; Dev tools<br>
    <small>TermuX → X11 → LinuX → Trixie → MATE</small>
  </p>
</div>

---

## ⚡ Why

Your Android phone is a pocket PC with 8GB+ RAM and an ARM64 CPU — it deserves a real desktop. If you've already fought your way through a manual proot install, you know where the pain is. arinanoLabs fixes it declaratively:

| Problem | arinanoLabs Solution |
|---------|----------------------|
| Chrome sleeps tabs | Firefox ESR desktop browser — stays alive |
| No glibc apps | Debian 13 proot — standard glibc |
| No dev tools | Node.js 22, Python 3, GCC, CMake built-in |
| Background killed | Termux:WakeLock keeps sessions alive |
| 30 min of apt + config | Python TUI installer, ~30s |
| Manual GPU config | Auto-detect GPU (Turnip/Panfrost/Virgl) |

**What this can't do:** no Docker, no systemd services, no native x86, no root (proot emulates root-like behavior, not real root). Full details in [Limitations](#️-limitations).

---

## 🚀 Quick Start

### Install (one-time)

```bash
curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/install.sh | bash
```

This bootstrapper will:
1. Check/install Python
2. Check/install `rich` library
3. Launch TUI installer

### Daily Use

```bash
alabs                  # Launch TUI menu
```

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

---

## 🏗️ How It Works

```
┌─────────────────────────────────────┐
│  USER LAYER (mutable)               │  ← Your packages, configs, data
│  VS Code, Chromium, etc.            │     Preserved across updates
├─────────────────────────────────────┤
│  CORE LAYER (declarative)           │  ← Built from Dockerfile in CI
│  Debian 13 + MATE + Firefox + dev   │     ghcr.io/arinadi/arinanolabs
└─────────────────────────────────────┘
```

### Python TUI Installer

Built with [Rich](https://github.com/Textualize/rich) for professional UX:

- **Pre-flight checks** — internet, storage, GPU, dependencies
- **GPU auto-detection** — Qualcomm Adreno → Turnip, ARM Mali → Panfrost
- **Self-healing mirrors** — auto-fallback if Termux repo is down
- **Progress bars** — real-time download speed + ETA

---

## 📦 What's Included

### In the image (ready to use)

| Category | Tools |
|----------|-------|
| 🌐 Browser | Firefox ESR |
| 🖥️ Desktop | MATE + Pluma + Caja |
| 🔧 Dev | Git, Node.js 22, Python 3, GCC, CMake |
| 📊 Sys | htop, tmux, OpenSSH |

### Extra Tools (via TUI menu)

| Category | Packages |
|----------|----------|
| 🌐 Browser | Chromium |
| 💻 IDE | VS Code (code-server), Neovim |
| 🖥️ System | Zsh + Oh My Zsh, Docker |
| 🔧 CLI | ripgrep, GitHub CLI |

---

## 🎮 GPU Acceleration

Auto-detected during install:

| GPU | Driver | Config |
|-----|--------|--------|
| Qualcomm Adreno | Turnip + Zink | Vulkan → OpenGL 4.6 |
| ARM Mali | Panfrost | OpenGL direct |
| Unknown | llvmpipe | Software fallback |

---

## 📂 Structure

```
arinanoLabs/
├── install.sh          ← Bootstrap entry point
├── install.py          ← Python TUI entry
├── alabs               ← Post-install TUI launcher
├── installer/          ← Python TUI modules
│   ├── menu.py         ←   Main menu
│   ├── install.py      ←   Install logic
│   ├── start.py        ←   Start/stop desktop
│   ├── gpu.py          ←   GPU detection
│   └── ...
├── image/              ← System definition (Dockerfile)
├── scripts/            ← CLI wrappers
├── launchers/          ← start/stop shortcuts
└── docs/               ← documentation
```

---

## ⚠️ Limitations

| Limitation | Workaround |
|-----------|------------|
| No root | proot provides root-like environment |
| No systemd | Start services manually |
| No GPU passthrough | virglrenderer auto-detected |
| ARM64 only | QEMU for cross-arch (slow) |
| No native X11 | Termux:X11 app required |
| No Docker | proot lacks kernel features |

---

## 🛑 Android 12+ Phantom Process Killer

Background processes can get killed by Android. Disable it:

- **Android 14+:** Developer Options → Disable child process restrictions
- **Android 12–13:** `adb shell settings put global settings_enable_monitor_phantom_procs false`

---

## 📜 License

GPLv3 — see [LICENSE](LICENSE).
