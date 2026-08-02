# Debug: MATE Desktop Black Screen After Stop/Start

> **Date:** 2026-08-02
> **Commits:** `7a33e18`..`9fb3276`
> **Symptom:** Stop works, start reports "MATE session running" but screen shows only X cursor

---

## Summary

The TUI menu option 2 (Stop) and option 1 (Start) had multiple issues that caused the desktop to appear as a black screen with only an X cursor, even though `pgrep -f mate-session` reported the session as running.

Three root causes were identified and fixed:

1. **`su - admin` login shell** overrode `XDG_RUNTIME_DIR` to `/tmp` (insecure mode 041777)
2. **`dbus-launch --sh-syntax` output** was redirected to log file, never evaluated by shell
3. **Stale dbus sockets** inside proot container's `/tmp` were never cleaned by stop

---

## Investigation Timeline

### Phase 1: Stop Not Killing Processes Properly

**Symptom:** After running stop, processes like proot wrapper and dbus-daemon survived.

**Root cause:** `stop_desktop()` had multiple issues:
- No explicit kill for proot wrapper processes (`proot --kill-on-exit ...`)
- No kill for orphaned `dbus-daemon` processes
- X11 socket cleanup used `rm -rf .X11-unix` which deleted the entire directory instead of just the socket file
- Stale dbus sockets in Termux TMPDIR were never cleaned
- Dead code after unreachable `return True`

**Fix (commits `7a33e18`, `edb8bbc`):**
- Added `pkill -9 -f 'proot.*arinanolabs'` and `pkill -9 -f dbus-daemon`
- Changed X11 cleanup to `rm -f .X0-lock` and `rm -f .X11-unix/X0` (keep directory)
- Added cleanup for stale dbus sockets and runtime dirs in both Termux TMPDIR and proot `/tmp`
- Made stop output verbose (shows each command result)
- Removed dead code

### Phase 2: Launcher Not Working From Home Directory

**Symptom:** `alabs` command worked inside the repo but not from `$HOME`.

**Root cause:** The `alabs` script used `cd "$(dirname "$0")"` which followed the symlink path (`~/bin/alabs`) instead of the real target (`~/arinanoLabs`).

**Fix (commit `7a33e18`):**
```bash
# Before
cd "$(dirname "$0")"

# After — resolve symlink first
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$SCRIPT_DIR"
```

### Phase 3: Black Screen — The Real Problem

**Symptom:** After clean stop, start reported "MATE session running" but screen was black. `pgrep -f mate-session` found the process, but no marco, mate-panel, caja, or any MATE components were running.

**Investigation steps:**

#### Step 1: Verify X11 socket sharing

```bash
# Check socket exists on host
ls -la $TMPDIR/.X11-unix/X0
# → srwxrwxrwx X0 ✓

# Check socket visible inside proot
proot-distro login arinanolabs --shared-x11 -- su admin -c 'ls -la /tmp/.X11-unix/'
# → X0 present ✓
```

X11 socket was properly shared via `--shared-x11` bind mount. Not the issue.

#### Step 2: Check MATE components installed

```bash
proot-distro login arinanolabs -- su admin -c 'which marco mate-session'
# → /usr/bin/marco ✓
# → /usr/bin/mate-session ✓
```

Components were installed. Not the issue.

#### Step 3: Check environment inside proot

```bash
proot-distro login arinanolabs -- su - admin -c 'echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"'
# → XDG_RUNTIME_DIR=/tmp    ← PROBLEM!
```

The `su - admin` (login shell) sourced `.bashrc` which hardcodes:
```bash
export XDG_RUNTIME_DIR=/tmp
```

`/tmp` has mode `041777` (world-writable). D-Bus rejects this as insecure:
```
dbus[PID]: Unable to set up transient service directory:
  XDG_RUNTIME_DIR "/tmp" can be written by others (mode 041777)
```

#### Step 4: Test with proper XDG_RUNTIME_DIR

```bash
proot-distro login arinanolabs --shared-x11 -- su - admin -c '
  export XDG_RUNTIME_DIR=/tmp/runtime-$$
  mkdir -p $XDG_RUNTIME_DIR && chmod 0700 $XDG_RUNTIME_DIR
  export DISPLAY=:0 ...
  exec dbus-launch --sh-syntax --exit-with-session mate-session
'
# → mate-session runs, but still no marco/panel. Log empty.
```

Setting `XDG_RUNTIME_DIR` properly removed the dbus warning, but mate-session still spawned no children. The log file remained empty.

#### Step 5: Analyze `dbus-launch --sh-syntax` behavior

The `--sh-syntax` flag makes `dbus-launch` output shell variable assignments:
```
DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/dbus-XXXX,guid=...
DBUS_SESSION_BUS_PID=12345
```

With `exec dbus-launch --sh-syntax --exit-with-session mate-session`, the output goes to **stdout** (the log file), not back into the shell environment. So `DBUS_SESSION_BUS_ADDRESS` is **never set** in the shell — mate-session starts without knowing where dbus is.

#### Step 6: The working combination

```bash
proot-distro login arinanolabs --shared-x11 -- su admin -c '
  export DISPLAY=:0 ...
  XDG=/tmp/runtime-$$ && mkdir -p $XDG && chmod 0700 $XDG
  export XDG_RUNTIME_DIR=$XDG
  eval $(dbus-launch --sh-syntax)
  exec mate-session
'
```

Three changes that made it work:

| Change | Why |
|--------|-----|
| `su admin` (no `-`) | Avoids login shell → `.bashrc` doesn't override `XDG_RUNTIME_DIR` to `/tmp` |
| `eval $(dbus-launch --sh-syntax)` | Evaluates dbus output in current shell → `DBUS_SESSION_BUS_ADDRESS` is set |
| `exec mate-session` | Replaces shell (not dbus-launch) → inherits the correct env |

**Result:** marco, mate-panel, clock-applet, notification-area, caja, mate-settings-daemon — all started. Desktop rendered on screen.

---

## Final Command

```python
# installer/start.py — start_mate()
inner_cmd = (
    f"export {exports} && "
    f"XDG=/tmp/runtime-$$ && mkdir -p $XDG && chmod 0700 $XDG && "
    f"export XDG_RUNTIME_DIR=$XDG && "
    f"eval $(dbus-launch --sh-syntax) && "
    f"exec mate-session"
)

cmd = (
    f"proot-distro login arinanolabs --shared-x11 -- "
    f"su admin -c '{inner_cmd}'"
)
```

---

## Files Changed

| File | Changes |
|------|---------|
| `installer/start.py` | Fixed `stop_desktop()` (verbose output, proot cleanup, dbus-daemon kill, X11 socket fix). Fixed `start_mate()` (dbus-launch eval, XDG_RUNTIME_DIR, su without login). |
| `installer/npyscreen_app.py` | Removed duplicate "Desktop started!" message. |
| `alabs` | Resolve symlink via `readlink -f` for reliable `cd` from anywhere. |
| `install.sh` | Fixed sed quoting for `$HOME/.local/bin` cleanup. |

---

## Key Learnings

1. **`su -` vs `su`** — The `-` flag starts a login shell that reads `.bash_profile`/`.profile`/`.bashrc`. In proot containers, `.bashrc` often overrides critical env vars. Use `su` (no `-`) when you need to control the environment yourself.

2. **`dbus-launch --sh-syntax`** — This outputs shell assignments to stdout. If you `exec` it, the output goes to the redirect target (log file), not into the shell. Use `eval $(dbus-launch --sh-syntax)` instead.

3. **XDG_RUNTIME_DIR** — D-Bus requires this directory to be mode `0700` (owner-only). `/tmp` is typically `041777` (world-writable sticky). Always create a dedicated subdirectory.

4. **Proot container cleanup** — Stale dbus sockets and runtime dirs accumulate in the proot container's `/tmp` across sessions. The stop function must clean both Termux TMPDIR and proot `/tmp`.

5. **`pgrep` false positive** — `pgrep -f mate-session` finding the process does NOT mean the desktop is functional. Always verify child processes (marco, mate-panel) exist.
