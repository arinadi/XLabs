<div align="center">
  <h1>📱 arinanoLabs</h1>
  <p><strong>Your phone is a Linux workstation — ~30s to a working desktop, not 30 minutes of apt.</strong></p>
  <p>
    <a href="https://arinano.work"><img src="https://img.shields.io/badge/site-arinano.work-blue"></a>
    <a href="https://github.com/arinadi/arinanoX/actions"><img src="https://img.shields.io/github/actions/workflow/status/arinadi/arinanoX/build-image.yml?label=build"></a>
    <a href="https://github.com/arinadi/arinanoX/blob/main/LICENSE"><img src="https://img.shields.io/github/license/arinadi/arinanoX"></a>
  </p>

  ```bash
curl -sL https://raw.githubusercontent.com/arinadi/arinanoLabs/main/bootstrap.sh | bash
```

  <img src="docs/arinanox-screenshot.jpg" alt="arinanoX desktop" width="360" style="border-radius:12px;">
  <p>
    Debian 13 &nbsp;·&nbsp; MATE &nbsp;·&nbsp; Firefox ESR &nbsp;·&nbsp; Dev tools<br>
    <small>TermuX&nbsp;→&nbsp;X11&nbsp;→&nbsp;LinuX&nbsp;→&nbsp;Trixie&nbsp;→&nbsp;MATE</small>
  </p>
</div>

---

## ⚡ Why

Your Android phone is a pocket PC with 8GB+ RAM and an ARM64 CPU — it deserves a real desktop. If you've already fought your way through a manual proot install, you know where the pain is. arinanoX fixes it declaratively:

| Problem | arinanoX Solution |
|---------|-------------------|
| Chrome sleeps tabs | Firefox ESR desktop browser — stays alive |
| No glibc apps | Debian 13 proot — standard glibc |
| No dev tools | Node.js 22, Python 3, GCC, CMake built-in |
| Background killed | Termux:WakeLock keeps sessions alive |
| 30 min of apt + config | Prebuilt image, ~580MB, extract and run |
| No rollback if update breaks | Atomic image swap, instant revert |

**What this can't do:** no Docker, no systemd services, no native x86, no root (proot emulates root-like behavior, not real root). Full details in [Limitations](#️-limitations) — read that before you invest time installing.

---

### Requirements

- Android ARM64 + [Termux](https://f-droid.org/en/packages/com.termux/) (F-Droid, NOT Play Store)
- [Termux:X11](https://github.com/termux/termux-x11/releases/tag/nightly) — display server
- [Termux:Widget](https://f-droid.org/en/packages/com.termux.widget/) (recommended — home screen launchers)

---

## 🏗️ How It Works

```
┌─────────────────────────────────────┐
│  USER LAYER (mutable)               │  ← Your packages, configs, data
│  VS Code, Chromium, etc.            │     Preserved across updates
├─────────────────────────────────────┤
│  CORE LAYER (declarative & reproducible) │  ← Built from Dockerfile in CI
│  Debian 13 + MATE + Firefox + dev   │     ghcr.io/arinadi/arinanolabs
└─────────────────────────────────────┘
```

### Declarative Image (NixOS-inspired)

The image is built from a **single Dockerfile** — your system as code, not a sequence of manual steps you have to remember and redo.

- 📦 **All packages and configs** defined declaratively in one file
- ⚙️ **MATE optimized for proot**: compositing off, power daemon removed
- 🎯 **Proot-aware**: systemd warnings suppressed, dbus locked down (mechanism detailed in [Protection Layers](#️-preventive-measures) below)
- ⚡ **CI-built and deployed** to GHCR on every push — image is exactly what's in the Dockerfile, every time

**Fresh reinstall:** `curl bootstrap.sh | bash` (~30s). User layer preserved via manifest.

| Concept | NixOS | arinanoX |
|---------|-------|-----------|
| System definition | `configuration.nix` | `image/Dockerfile` |
| Packages | declarative list | `RUN apt-get install` |
| Reproducible | yes (closures) | yes (CI + GHCR) |
| User overlays | home-manager | `arinanox install`, `user-manifest.yaml` |

**Base:** Debian 13 (Trixie). Firefox ESR from native repos — zero external APT sources.

### Prebuilt vs DIY

If you've done the manual route before, this is the actual delta:

| | arinanoX (prebuilt) | DIY (manual install) |
|---|---|---|
| Download | ~580 MB (1 image) | ~450 MB (base distro) + packages |
| Install time | ~30s on decent connection/storage — extract + setup, no compiling | 20–30 min (apt + config + theme) |
| MATE desktop | configured, ready | must install + configure |
| Proot fixes | compositing off, warnings suppressed, power daemon removed | trial-and-error |
| Updates | `curl bootstrap.sh \| bash` (~30s) | re-do everything |

---

## 📦 Built-In + Extras

### In the image (ready to use)

| Category | Tools |
|----------|-------|
| 🌐 Browser | Firefox ESR |
| 🖥️ Desktop | MATE + Pluma (editor) + Caja (file manager) |
| 📝 Apps | Pluma (editor), Eye of MATE (images) |
| 🔧 Dev | Git, Node.js 22 LTS, Python 3 (pip/venv/dev), GCC, Make, CMake |
| 📊 Sys | htop, tmux, OpenSSH |
### CLI extras (patch.sh)

```bash
bash ~/.arinanox/scripts/patch.sh --chromium --code --zsh
```

| Category | Packages |
|----------|----------|
| 🌐 Browser | Chromium |
| 💻 IDE | VS Code (code-server), Geany, Neovim |
| 🖥️ System | Zsh + Oh My Zsh, Nala |
| 🔧 CLI | ripgrep, GitHub CLI |
| 🎨 GUI | Viewnior, Xarchiver, Galculator |

---

## 🚀 Usage

```bash
arinanox start        # One-command launch
arinanox stop         # Stop everything
arinanox status       # System overview
arinanox doctor       # Full health-check
arinanox backup       # Backup to /sdcard
arinanox snapshot     # Instant checkpoint (hardlinked)
arinanox update       # Fresh image + re-apply configs
arinanox help         # All commands
```

### 🎮 GPU Acceleration (virglrenderer)

arinanoX auto-detects the best GPU path (3-tier):

```
1. android           → virgl_test_server_android      (native GLES)
2. angle-vulkan-null → virgl + ANGLE passthrough       (Vulkan GPUs)
3. CPU fallback      → LIBGL_ALWAYS_SOFTWARE=1
```

| Mode | Env | Performance |
|------|-----|-------------|
| GPU (virgl) | `GALLIUM_DRIVER=virpipe` | 4K video, 3D games |
| CPU (fallback) | `LIBGL_ALWAYS_SOFTWARE=1` | Desktop only |

### 📱 Termux:Widget (1-tap launchers)

| Shortcut | Action |
|----------|--------|
| 🟢 `1-start-arinanox.sh` | Full startup |
| 🔴 `0-stop-arinanox.sh` | Full stop |

### 🔄 Update (preserves user config via manifest)

```bash
arinanox snapshot create    # Checkpoint first
arinanox update              # Fresh image + re-apply user-manifest.yaml
```

### Declarative User Layer

`~/.arinanox/user-manifest.yaml` tracks your packages and dotfiles. Auto-generated by snapshot, auto-reapplied after update.

```bash
arinanox install  # Apply packages from manifest
```

---

## 🛡️ Preventive Measures

### Termux Bind-Mount

Termux binaries (`/data/data/com.termux/files/usr/bin/...`) are bind-mounted into the proot container, but **cannot be executed** due to different linker/libc:
- Termux: bionic libc (Android NDK)
- Proot: glibc (Debian)

The container PATH correctly points to `/usr/bin/` (proot-native). This is the exact class of bug that eats hours in a manual proot setup.

### Protection Layers

| Layer | Mechanism | Location |
|---|---|---|
| **1. PATH hardening** | `.bashrc` sets clean PATH + guard strips Termux paths at end of init | `~/.bashrc`, `image/configs-target/home/admin/.bashrc` |
| **2. Runtime audit** | `arinanox doctor` checks every binary + PATH — warns if Termux found | `~/.arinanox/scripts/doctor.sh` |
| **3. PROOT_NO_SECCOMP** | Fix fork/futex/libuv for Node.js tools (Pi, ddg_search, playwright) | `~/.shortcuts/1-start-arinanox.sh` |
| **4. Documentation** | Bind-mount explanation + how to audit | `README.md` |

These four layers are also what's behind the "warnings suppressed" claim in the sections above — they're not silenced blindly, they're intercepted at a known cause.

Check status anytime:
```bash
bash ~/.arinanox/scripts/doctor.sh
```

---

## ⚠️ Limitations

| Limitation | Workaround |
|-----------|------------|
| No root | proot provides root-like environment, not real root |
| No systemd | Start services manually; power-manager removed |
| No GPU passthrough | virglrenderer auto-detected (3-tier: android → angle → CPU) |
| ARM64 only | QEMU user-mode for cross-arch, with a performance cost |
| No native X11 | Termux:X11 app required |
| Storage restrictions | `termux-setup-storage` |
| **Cannot do** | Docker containers (daemon needs kernel features proot doesn't have), systemd services, x86 natively |

---

## 🛑 Android 12+ Phantom Process Killer

Background processes (including your desktop session) can get silently killed by Android's process limiter. Disable it:

- **Android 14+:** Developer Options → Disable child process restrictions
- **Android 12–13:** `adb shell settings put global settings_enable_monitor_phantom_procs false`

---

## 📂 Structure

```
arinanoX/
├── bootstrap.sh          ← one-command entry point
├── image/                ← 🎯 System definition (Dockerfile)
│   ├── Dockerfile        ←    declarative: packages, configs
│   └── configs-target/    ←    bash configs
├── scripts/              ← setup, patch, status
├── launchers/             ← start/stop shortcuts
├── docs/                  ← documentation
└── .github/workflows/     ← CI → GHCR image on push
```

---

## 🖱️ Right-Click on Touchscreen

`Ctrl+Alt+R` triggers right-click via xdotool (auto-installed).

Add to `~/.termux/termux.properties`:
```properties
extra-keys = [ \
 ['ESC','/',{key: '-', popup: '|'},'HOME','UP','END','PGUP',{macro: "CTRL ALT r", display: "🖱️R"}], \
 ['TAB','CTRL','ALT','LEFT','DOWN','RIGHT','PGDN','KEYBOARD'] \
]
```

Run `termux-reload-settings` after saving.

---

## 📜 License

GPLv3 — see [LICENSE](LICENSE).
