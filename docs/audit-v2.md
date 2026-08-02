# Audit: arinanoLabs v2.0

> **Date:** 2026-08-02  
> **Branch:** v2

---

## Project Structure

```
arinanoLabs/
├── install.sh              # Bootstrap entry point (curl | bash)
├── install.py              # Python entry point
├── VERSION                 # "2.0.0"
├── requirements.txt        # rich, requests
├── installer/              # Python TUI package
│   ├── __init__.py
│   ├── ui.py               # Shared UI components
│   ├── menu.py             # Main TUI menu
│   ├── welcome.py          # Welcome/installed screens
│   ├── preflight.py        # Pre-flight checks
│   ├── mirror.py           # Mirror fallback
│   ├── gpu.py              # GPU detection
│   ├── install.py          # Install logic
│   └── start.py            # Start/stop desktop
├── scripts/                # Legacy shell scripts
│   ├── doctor.sh           # Health check
│   ├── host-setup.sh       # Host packages
│   ├── launcher-gen.sh     # Launcher setup
│   ├── manifest-apply.sh   # Apply user manifest
│   ├── manifest-generate.sh # Generate manifest
│   ├── motd-setup.sh       # MOTD setup
│   ├── patch.sh            # Extra packages
│   ├── seccomp-check.sh    # Seccomp check
│   ├── seccomp-fix.sh      # Seccomp fix
│   └── user-snapshot.sh    # User snapshots
├── image/                  # Docker image
│   ├── Dockerfile
│   └── configs-target/
├── docker/dev/             # Dev environment
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── dev.sh
├── bootstrap.sh            # Legacy installer
├── uninstall.sh            # Uninstaller
├── test-tui.sh             # Podman test script
└── docs/                   # Documentation
```

---

## Feature Checklist

| Feature | Status | File |
|---------|--------|------|
| Pre-flight checks | ✅ | `installer/preflight.py` |
| GPU auto-detect | ✅ | `installer/gpu.py` |
| Mirror fallback | ✅ | `installer/mirror.py` |
| Welcome TUI | ✅ | `installer/welcome.py` |
| Main menu TUI | ✅ | `installer/menu.py` |
| Install flow | ✅ | `installer/install.py` |
| Start/stop desktop | ✅ | `installer/start.py` |
| Progress UI | ✅ | `installer/ui.py` |
| Self-update | ⏳ TODO | — |
| Extra tools menu | ⏳ TODO | — |
| Uninstall | ⏳ TODO | — |

---

## Test Instructions (Podman on PC)

### Prerequisites

1. Install Podman Desktop or Podman CLI
2. Initialize Podman machine:
   ```bash
   podman machine init
   podman machine start
   ```

### Quick Test

```bash
# From project root
bash test-tui.sh
```

### Manual Test

```bash
# 1. Build dev container
podman build -t arinanolabs-dev -f docker/dev/Dockerfile docker/dev

# 2. Run container with project mounted
podman run -it --rm \
  -v "D:\arinanoX:/data/data/com.termux/files/home/arinanoLabs" \
  arinanolabs-dev bash

# 3. Inside container, install deps and run TUI
cd /data/data/com.termux/files/home/arinanoLabs
pip install rich requests
python install.py
```

### Test Matrix

| Test | Command | Expected |
|------|---------|----------|
| TUI launches | `python install.py` | Welcome screen appears |
| Pre-flight runs | Select [1] Install | Checks pass |
| GPU detected | During install | Shows vendor/driver |
| Menu works | After install | 6 options shown |
| Start desktop | Select [1] | Processes start |
| Stop desktop | Select [2] | Processes stop |
| Status | Select [5] | Shows container info |

---

## Known Issues

1. **No X11 in Podman** — Desktop won't actually start (no display server)
2. **No proot-distro** — Install will fail at container creation step
3. **Termux packages** — `pkg` not available in Debian container

**Solution:** Test TUI flow only, not actual desktop launch.

---

## Files Summary

| Category | Count | Size |
|----------|-------|------|
| Python installer | 8 files | ~35 KB |
| Shell scripts | 11 files | ~25 KB |
| Config/Docker | 5 files | ~10 KB |
| Docs | 3 files | ~15 KB |
| **Total** | **27 files** | **~85 KB** |
