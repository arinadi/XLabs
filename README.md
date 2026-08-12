<div align="center">
  <h1>📱 XLabs</h1>
  <p><strong>Your phone is a Linux workstation — ~30s to a working desktop, not 30 minutes of apt.</strong></p>
  <p>A full Debian 13 + XFCE desktop inside Termux, no root — installed and
  driven from a touch-friendly TUI, not a wall of shell scripts.</p>
  <p>
    <a href="https://github.com/arinadi/XLabs/actions"><img src="https://img.shields.io/github/actions/workflow/status/arinadi/XLabs/build-image.yml?label=build"></a>
    <a href="https://github.com/arinadi/XLabs/blob/main/LICENSE"><img src="https://img.shields.io/github/license/arinadi/XLabs"></a>
    <a href="https://github.com/arinadi/XLabs/commits/main"><img src="https://img.shields.io/github/last-commit/arinadi/XLabs"></a>
    <a href="https://github.com/arinadi/XLabs/stargazers"><img src="https://img.shields.io/github/stars/arinadi/XLabs"></a>
  </p>

  ```bash
  curl -sL https://raw.githubusercontent.com/arinadi/XLabs/main/install.sh | bash
  ```

  <img src="docs/arinanox-screenshot.jpg" alt="XLabs desktop" width="360" style="border-radius:12px;">
  <p>
    Debian 13 &nbsp;·&nbsp; Xfce4 &nbsp;·&nbsp; Firefox ESR &nbsp;·&nbsp; Dev tools<br>
    <small>TermuX → X11 → LinuX → Trixie → Xfce4</small>
  </p>
</div>

---

## ⚡ Why

Your Android phone is a pocket PC with 8GB+ RAM and an ARM64 CPU — it deserves a real desktop. If you've already fought your way through a manual proot install, you know where the pain is. XLabs fixes it declaratively:

| Problem | XLabs Solution |
|---------|----------------------|
| Chrome sleeps tabs | Firefox ESR desktop browser — stays alive |
| No glibc apps | Debian 13 proot — standard glibc |
| 30 min of apt + config | Pre-built OCI image, pulled in one step |
| Fiddly X11 + audio + dbus startup | One menu entry, with cleanup on stop |
| Teardown that leaves stale locks | One teardown path, verified before it reports success |

**What this can't do:** no Docker, no systemd services, no native x86, no root (proot emulates root-like behavior, not real root). Full details in [Limitations](#️-limitations).

---

## 🌱 Design

The install path is a from-scratch Python
[Textual](https://github.com/Textualize/textual) TUI instead of shell scripts —
idempotent, resumable, with [more than 30 automated tests](tests/run_tests.py)
run on every push. The system image is declarative: a `Dockerfile`, built and
published by CI, not a setup script run against whatever state the device
happens to be in. And **Doctor** diagnoses and repairs specific, named failure
modes — the Debian security-archive bug, DNS, timezone, Electron's sandbox
under proot, per-device GPU and audio method selection — rather than leaving
you to re-run an install script and hope.

DroidDesk covers more ground: a choice of desktop environment, Adreno-specific
GPU paths, monitor/VNC bridging. XLabs deliberately narrows to one path —
Debian 13 and XFCE4 — and puts the effort into that path working reliably
instead. Both are GPLv3; credit and thanks to DroidDesk for the idea and the
starting point.

---

## 🚀 Quick Start

### Install (one-time)

```bash
curl -sL https://raw.githubusercontent.com/arinadi/XLabs/main/install.sh | bash
```

`install.sh` is deliberately thin — it gets git, Python, and this repo onto the
machine, then hands over to `~/XLabs/install.py`, which does the rest:
Python libraries, Termux packages (proot-distro, Termux:X11, PulseAudio,
graphics), the Debian container, and the `xlabs` launcher.

The launcher is symlinked into `$PREFIX/bin`, which is Termux's entire default
PATH — so `xlabs` works immediately, in the session that ran the installer, with
no shell startup file touched. Off Termux it falls back to `~/bin` and adds that
to PATH in both `.bashrc` and `.profile`.

It runs unattended and is safe to re-run — each step skips work already done,
so a partial install can be resumed by running it again.

**One thing it cannot do for you:** the desktop renders inside the
[Termux:X11 Android app](https://github.com/termux/termux-x11/releases/tag/nightly),
which has to be sideloaded — `pkg` only provides the Termux half. The installer
checks for it and says so at the end if it is missing, and Doctor reports it too.

Then open a new terminal session:

### Daily Use

```bash
xlabs                  # Launch the TUI
```

The menu is sized for a thumb:

| | | |
|---|---|---|
| **Start Desktop** | **Stop Desktop** | |
| Update | Tools | Settings |
| Doctor | Backup | |
| Reset | Cache | |

Everything is tappable — Termux delivers touches as mouse events. Full
reference below in [The TUI, screen by screen](#-the-tui-screen-by-screen).

---

## 🏗️ How It Works

Two layers. The **core** is declarative — defined by `image/Dockerfile`, built in
CI, published to `ghcr.io/arinadi/xlabs`. The **user layer** is whatever
you install inside the running container; it survives across desktop restarts,
but a Reset wipes it.

Every pull tries GHCR first and falls back to Docker Hub automatically if
that fails. GHCR has no rate limit for a public package, which matters more
than raw speed: most installs happen over mobile data behind carrier-grade
NAT, where Docker Hub's anonymous-pull limit (10/hour as of 2026) is shared
with every other subscriber on the same IP, not just this install. Docker
Hub is genuinely faster for some ISPs — ghcr.io routes through Fastly's
AnyCast CDN, which some ISPs peer with badly — so it stays as a fallback
rather than being dropped.

Starting the desktop is a chain, and each link is cleaned up in reverse on stop:

```mermaid
flowchart LR
    A[PulseAudio] --> B["Shared socket<br/>$PREFIX/tmp/pulse-socket"]
    B --> C[virgl renderer]
    C --> D[termux-x11 :0]
    D --> E{X11 socket<br/>ready?}
    E -->|yes| F["proot-distro login<br/>--user admin --shared-tmp"]
    E -->|timeout 5s| F
    F --> G["dbus-launch --exit-with-session<br/>startxfce4"]
```

### Python TUI

Built with [Textual](https://github.com/Textualize/textual). Every action runs
in a thread worker, so a ten-minute image pull streams into a log pane while
the interface stays live.

Every screen returns to the menu, and anything destructive is gated behind a
confirmation first:

```mermaid
stateDiagram-v2
    [*] --> MainScreen

    MainScreen --> ActionScreen: Start · Stop · Update
    MainScreen --> DoctorScreen: Doctor
    MainScreen --> ToolsScreen: Tools
    MainScreen --> BackupScreen: Backup
    MainScreen --> SettingsScreen: Settings
    MainScreen --> ConfirmScreen: Reset · Cache

    ToolsScreen --> ConfirmScreen: Install
    DoctorScreen --> DupesScreen: Dupes
    DupesScreen --> ConfirmScreen: Remove
    BackupScreen --> ConfirmScreen: Backup now · Restore · Delete

    ConfirmScreen --> MainScreen: Cancel
    ConfirmScreen --> ActionScreen: Confirm

    DoctorScreen --> ActionScreen: Fix · Diagnose

    ToolsScreen --> MainScreen: Back
    DoctorScreen --> MainScreen: Back
    DupesScreen --> DoctorScreen: Back
    BackupScreen --> MainScreen: Back
    SettingsScreen --> MainScreen: Back
    ActionScreen --> MainScreen: Back, once idle
```

`ActionScreen` is where the long work happens. It hands the job to a thread so
the terminal keeps redrawing, and refuses to be dismissed until that thread is
done — leaving mid image pull would strand a half-installed container:

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Screen as ActionScreen
    participant Worker as Thread worker
    participant Proc as Subprocess

    User->>Screen: choose an action
    Screen->>Screen: mount · busy = true · Back disabled
    Screen->>Worker: run_task()

    Worker->>Proc: stream_cmd(cmd)
    loop each output line
        Proc-->>Worker: stdout
        Worker-->>Screen: call_from_thread(write)
    end
    Note over Worker,Proc: a watchdog kills the whole<br/>process tree at the timeout

    Proc-->>Worker: exit code
    Worker->>Screen: finish · busy = false · Back enabled

    User->>Screen: Back or Escape
    Screen-->>User: return to the menu
```

---

## 🖥️ The TUI, screen by screen

<!-- screenshot: main menu -->

Built for a thumb, not a mouse: full-width buttons, generous spacing between
them, and every Back sits at the bottom of its screen — reachable one-handed,
in the same place every time.

One thing no TUI can control from inside itself: a button's *physical* touch
size depends on Termux's terminal font size, since height is measured in
character cells, not pixels. At Termux's default font size a 3-row button
comfortably clears the 44-48dp minimum most mobile guidelines recommend; below
roughly **10sp** it starts getting tight. If buttons feel small enough to
mistap, that is what to raise — pinch-to-zoom in the terminal, or Termux's
Style menu — not something XLabs can fix from the Python side.

### Start Desktop

Brings the whole stack up in order, streaming each step:

1. **Wake lock** — `termux-wake-lock`, so Android does not freeze the session
2. **Audio server** — PulseAudio plus a Unix socket in the shared tmp, which
   is what the container opens
3. **virgl renderer** — first one that exists, or software rendering
4. **ICE socket directory** — `/tmp/.ICE-unix`, which `xfce4-session` needs to
   accept its own children and which nothing else on this stack creates
5. **X11 server** — `termux-x11 :0`, then opens the Termux:X11 app
6. **Wait for the socket** — until it accepts a connection, not merely exists
7. **Session** — `dbus-launch --exit-with-session xfce4-session` as `admin`

It always runs a full stop first, even when nothing appears to be running.
Leftovers outlive the session that made them, and a stale `.X0-lock` or an
orphaned proot is exactly what breaks the next start.

If the desktop does not come up, a **full diagnostic report is collected
automatically** — no need to go and ask for it. With no container installed,
Start offers to pull one instead of failing further down.

### Stop Desktop

<!-- screenshot: stop -->

Innermost first, which is the opposite of what feels natural:

1. `TERM` then `KILL` this container's proot tree — proot runs with
   `--kill-on-exit`, so that takes everything inside with it
2. X11 down, then the Android app force-stopped
3. `pulseaudio --kill`, virgl down
4. Sweep anything that outlived its parent
5. Remove sockets, lock files and runtime directories

There is no polite logout step. `xfce4-session-logout` reaches the session
manager over its D-Bus and ICE sockets, and a fresh `proot-distro login` has
neither, so the request never arrived — every stop just waited eight seconds
and then killed anyway. `TERM` before `KILL` still lets the tree exit on its
own.

Then it **verifies with `pgrep` and tells you what survived**, rather than
printing "Stopped" regardless.

### Update

`git pull --ff-only`, falling back to a hard reset on `origin/main` when the
fast-forward is refused. When it finishes, a **Restart** button relaunches
`xlabs` on the code that was just pulled — pulling into a running process
otherwise does nothing, since the old modules are already loaded.

### Tools

<!-- screenshot: tools search -->

A package browser for the container.

Type a name and press Enter to search the container's package lists. Results
show an **I** against anything already installed, then highlight a row and
press **Install**. apt runs inside the container with its output streamed;
Termux is not touched.

The first search fetches the package lists, which takes a moment. The image
ships without them — every Dockerfile layer ends with
`rm -rf /var/lib/apt/lists/*` to keep the download small — so without this
every search would match nothing and read as "no such package".

An output pane below the results shows the command and its raw output, because
a failed search and an empty one otherwise look identical.

**Mirror** switches which Debian mirror the container fetches from. Debian
13's `debian.sources` carries the main archive and security as two separate
stanzas at different paths; repointing both at a mirror sends security
requests somewhere it likely does not carry, and `apt update` exits 100 — the
usual meaning of that error right after a switch. Security is identified by
its `Suites:` field and always forced back to `security.debian.org`, never to
the chosen mirror. If the new mirror still fails, the previous sources are
restored automatically.

Identifying the security stanza by its `Suites:` field rather than by
inspecting its URI matters once a container has already been broken by an
older switch: a URI that has been repointed at an unrelated mirror carries no
hint that it was ever security, so the earlier fix repaired the file the first
time and then quietly re-broke it on every switch after — restoring whatever
value it found, which was the corrupted one. `Suites:` does not change, so it
is the only signal used now, and Doctor reports the security archive on its
own besides. The list is
not hardcoded: **Refresh** pulls Debian's own deb822 masterlist and keeps the
nearby countries, and **Measure** times a real download from each and sorts by
throughput. `netselect-apt` does something similar but ranks by latency and
writes the old sources format, neither of which suits a phone on mobile data.

**Repos** adds third-party apt repositories, each with its own signing key
under `/etc/apt/keyrings` so apt verifies it the way it verifies Debian:

| Repo | What it gives you |
|------|-------------------|
| `backports` | Newer packages from Debian itself — no new key |
| `mozilla` | Firefox tracking release rather than ESR |
| `vscode` | Visual Studio Code |

**Add** takes any repository: name, URI, suites, components, and a signing key
URL. The key is mandatory — a repository signed by nothing apt already trusts
cannot be verified, and pointing it at Debian's own key would not help, since
the signature simply would not match. Every field is validated before
anything is written: the name cannot collide with a built-in repo or one
already added, and none of the fields may contain a newline, which could
otherwise smuggle a second directive into the stanza. Repos added by an
earlier session, or by hand under the `xlabs-` naming convention, show
up in the list too.

Search terms and package names are validated against the Debian package-name
shape and rejected rather than escaped — they end up in a shell command.

### Doctor

<!-- screenshot: doctor -->

There used to be a separate Status screen. It duplicated more than half of
Doctor's own checks with none of the fixes, so it is gone — its facts are
folded in here instead, alongside a Diagnose/Fix that Status never had.

Internet, Python, repository checkout, launcher target, Textual, proot-distro,
PulseAudio, Termux:X11, the GPU renderer, the X11 app, the container, storage,
DNS, timezone, audio, the security archive, Electron apps' sandbox, Firefox's
video defaults, and stale X11 sockets — plus a line up top with whatever does
not fit the ok/broken shape of an Issue: whether the desktop is running, image
cache size, and the version.

Three states, not two: ● present, ○ missing, and **? for could not tell**.
Querying installed Android apps is unreliable from Termux, and reporting
"missing" when the honest answer is "unknown" sends you fixing the wrong thing.

**GPU renderer** is `virglrenderer-android`. Without it the desktop runs on
llvmpipe — everything is drawn on the CPU.

**Storage** reuses the same free-space check the installer runs before
pulling the image, at a lower floor: once a container exists, apt's own
cache is the only space a repair can free without deleting something you
put there yourself, so that is all the fix does — `apt-get clean` and
`autoremove`.

**DNS** failures inside the container read exactly like a dead mirror —
`apt-get update` fails with "Temporary failure in name resolution" even
though the connection itself is fine. The usual cause is `resolv.conf`
being empty or a dangling symlink (some images ship one pointing at
systemd-resolved, which does not run under proot). The repair replaces it
with `1.1.1.1` and `8.8.8.8`.

**Timezone** is UTC in the image and nothing ever points it at the device's
own zone, so file timestamps and a terminal's clock inside the container
silently disagree with Android's. The repair reads the device's zone with
`getprop persist.sys.timezone` and symlinks `/etc/localtime` to match.

**Electron apps** (VS Code, and anything else built on Electron) open nothing
at all under proot: their SUID sandbox needs unprivileged user namespaces,
which proot only fakes without a kernel behind them, so Chromium's zygote
sandbox init fails before the window ever appears. The repair finds every
installed Electron app by its `chrome-sandbox` helper — not by name, so
whatever gets installed later is caught too — and adds `--no-sandbox` to its
`.desktop` launcher. proot is already the outer isolation boundary on a
personal device, so there is nothing behind the sandbox worth protecting.

Firefox's video defaults are the fix for stuttering YouTube. There is no
VA-API through proot, so VP9 and AV1 are decoded on the CPU — and that, not
rendering, is what makes playback bad. The repair drops a preferences file
into the container that turns both off, so YouTube falls back to H.264. They
are defaults rather than locks: `about:config` still wins.

VirGL does not solve this. It accelerates OpenGL, and the cost of a video is in
decoding it.

**Audio** works the same way as Bench, because no single method works
everywhere. Three have failed here already: TCP where the module loaded but
nothing listened, a Unix socket that connected and then failed its handshake,
and shared memory that does not survive the proot boundary.

So the methods are declared and tested end to end, and the one that plays is
written to `.env` and used by every later start:

| Method | Transport |
|--------|-----------|
| `unix` | Socket in the shared tmp, shared memory off |
| `unix-shm` | Same socket, shared memory on |
| `tcp` | Loopback TCP, shared memory off |
| `tcp-shm` | Loopback TCP, shared memory on |

It plays from Termux first. If that fails, nothing in the container will help
and it stops there rather than testing four methods against a dead sink.

**Bench** answers a question this project could not answer from the outside.
The published guidance is written for Qualcomm hardware — zink is reported to
work only there, Turnip is Adreno-only — so on an Exynos or Mali device the
right configuration is genuinely unknown.

So it measures. glmark2 runs under each configuration in turn and the winner
is written to `.env`, to be used by every later start:

| Preset | Path |
|--------|------|
| `software` | llvmpipe — the baseline that says whether acceleration helped |
| `virgl` | `virgl_test_server_android`, works on most devices |
| `angle` | virgl → ANGLE → Vulkan, the Mali path |
| `angle-null` | ANGLE with the null Vulkan loader |
| `zink` | OpenGL on Vulkan, reported to work only on Qualcomm |

It needs termux-x11 running, but not the desktop.

**Recording is not possible**, and no amount of configuration changes that. The
Termux app does not declare `android.permission.RECORD_AUDIO`, so PulseAudio
has no microphone source — `module-sles-source` fails to initialise, and
forcing it yields silence rather than audio. `termux-microphone-record` from
Termux:API works, but it is a separate app and cannot feed the container.

| Button | What it does |
|--------|--------------|
| **Re-scan** | Run the checks again |
| **Fix (N)** | Repair everything repairable, in one press |
| **Diagnose** | The same full report Start prints when it fails |
| **Dupes** | Tools installed in both Termux and the container |
| **Audio** | Play a test tone from Termux, then from the container |
| **Bench** | Measure each GPU configuration and keep the fastest |

Only genuinely fixable problems are counted in **Fix**. Anything needing you —
a missing APK, no checkout — says so instead of offering a button that cannot
help.

**Diagnose** reports host processes and sockets, then probes inside the
container: the admin user, the session binaries, the shared socket, `xset q`
against the display, and a foreground session run. It ends with a short guide
to reading it.

**Dupes** lists tools present on both sides and can uninstall the Termux
copies, treating the container as primary. Only packages the container is
confirmed to provide are offered, nothing XLabs itself needs is ever a
candidate, and it is deliberately not part of **Fix** — removing packages from
your Termux is a decision, not a repair.

### Settings

<!-- screenshot: settings -->

Per-device preferences, saved to `.env`. Each value is owned by whatever
module actually uses it — this screen only reads and writes them through
that module's own functions, so there is exactly one place that knows what
a value means.

| Setting | What it changes |
|---------|------------------|
| Debian mirror | Shown, not edited — pick one from Tools → Mirror. Shown here so it does not need to be two places that could disagree. |
| Audio method | Overrides what Doctor → Audio measured (`unix` / `unix-shm` / `tcp` / `tcp-shm`), for when auto-detection picked wrong or a method stops working after a Termux/Android update. |
| GPU profile | Overrides what Doctor → Bench measured. Picking one manually clears the recorded benchmark score — a score from a *different* profile would misreport the override as measured. |
| termux-x11 rendering | `-legacy-drawing` and `-force-bgra`, normally invisible to this app entirely. Some devices show a black screen (fixed by legacy drawing, which skips the modern Android hardware-buffer path) or swapped color channels (fixed by force-BGRA); neither is detectable from software, only by looking at the screen. |

**Mirror** gets special treatment beyond just being shown: choosing one from
Tools → Mirror now saves it, and it is automatically reapplied right after
any fresh container install — Reset would otherwise silently revert to the
default mirror and throw away a measured choice every time.

Every change here needs a desktop restart to take effect — none of these
are read while a session is already running.

### Backup

<!-- screenshot: backup -->

Archives and restores `/home/admin` — dotfiles, the Firefox profile, editor
settings, the XFCE panel layout, anything installed or configured as the
regular user. Not apt packages: those come back with a normal install, and
re-archiving them would just be a slower way to redo what apt already does.

Both directions run `tar` **through the container**, not as a host-side file
copy. proot fakes ownership and backs some files with a hardlink-emulation
store (`rootfs/.l2s`) that a raw copy of the underlying files would not
reproduce — `tar` running inside a proot login sees the same logical
filesystem any other program in the container does.

A backup is a timestamped `.tar.gz` under `~/XLabs-backups` on Termux's
own storage — outside the container, so a **Reset** cannot take it down too.
**Restore** replaces `/home/admin` with the archive's contents; the home it
replaces is kept as `/home/admin.bak` inside the container rather than
deleted, in case the wrong archive gets picked.

The natural pairing is Backup before **Reset**: back up, wipe and reinstall
the container, then Restore once it is back up.

### Reset and Cache

**Reset** deletes the container and pulls a fresh image. **Cache** drops
downloaded OCI layers and keeps the container. Both go through a confirmation
that spells out what is lost.

### Copying anything

Every screen that produces output — logs, Doctor, Dupes, Tools, Backup, Settings — has a
**C** button and a `c` key. It tries the Android clipboard via
`termux-clipboard-set`, then the terminal's own OSC 52, and **always mirrors
the text to a file** as well, because the usual reason to copy a failure is to
paste it somewhere for help and neither clipboard is guaranteed.

The button is a letter rather than a clipboard glyph — Termux's font cannot be
relied on to have one.

### Keys

| Key | Where |
|-----|-------|
| `q` | Quit, from the menu |
| `Escape` | Back — refused while an action is still running |
| `c` | Copy the screen's output |
| `Enter` | Run the search, in Tools |

The layout holds down to a 36-column terminal, well under a typical Termux
portrait width. A test drives every screen at 40, 45 and 60 columns.

---

## 📦 What's Included

### In the image

The image is currently a **vanilla baseline**, deliberately. It matches the
established Termux + proot + XFCE recipe and adds nothing beyond a browser:

| Category | Packages |
|----------|----------|
| 🖥️ Desktop | `xfce4`, `xfce4-terminal`, `dbus-x11` |
| 🌐 Browser | `firefox-esr` |
| 🎮 Graphics | Mesa userspace, `x11-xserver-utils`, `mesa-utils` |
| 🔊 Audio | `pulseaudio-utils` (client; the server runs in Termux) |
| 🧱 Base | `ca-certificates`, `locales`, `sudo` |

Installed **with** recommends, as every published guide does. An earlier image
used `--no-install-recommends` throughout and produced a container where
`xfce4-session` started but never launched `xfwm4` or `xfdesktop`.

`xfce4`'s own Recommends — as opposed to the Depends that make up the session
itself — are `desktop-base`, `mate-polkit`, `tango-icon-theme`,
`thunar-volman` and `xfce4-notifyd`. Two are excluded: `desktop-base`
(Debian's splash/wallpaper artwork, purely cosmetic) and `thunar-volman`
(auto-mounts removable media — nothing to mount here). The other three stay:
they are either visible (notifications, panel/file-manager icons, the
privilege-elevation dialog) or close enough to the recommends that fixed the
launch bug above that trimming them needs a real device test, not a guess
from a dependency list.

The dev toolchain, Zsh, on-screen keyboard, theming and the pre-baked panel
layout were removed to get back to a build of known-good shape. They are in git
history and come back once the baseline is confirmed working.

Anything else is a search away in [Tools](#tools).

---

## 🎮 Graphics

There is no GPU vendor detection. The start sequence probes for a virgl
renderer and takes the first one that exists:

| Probe | Used when |
|-------|-----------|
| `virgl_test_server_android` | present on `PATH` (Termux `virglrenderer-android`) |
| ANGLE `vulkan-null` backend | `$PREFIX/opt/angle-android/vulkan-null` exists |
| ANGLE `vulkan` backend | `$PREFIX/opt/angle-android/vulkan` exists |
| none | falls back to software rendering |

The container ships Mesa userspace (`libgl1-mesa-dri`, `libglx-mesa0`,
`mesa-utils`) so OpenGL works either way.

---

## 📂 Structure

```
XLabs/
├── install.sh          ← Bootstrap: git, Python, repo checkout
├── install.py          ← Full installer
├── xlabs               ← TUI launcher
├── installer/          ← TUI package
│   ├── app.py          ←   Textual app: screens, runners
│   ├── app.tcss        ←   Styling
│   ├── start.py        ←   Desktop lifecycle
│   ├── preflight.py    ←   Environment checks (pure stdlib)
│   ├── system.py       ←   Subprocess helpers
│   └── const.py        ←   Paths and names
│   └── doctor.py       ←   Diagnosis and repair
│   ├── bench.py        ←   GPU benchmark and profile
│   ├── config.py       ←   .env, per-device settings
├── image/              ← System definition (Dockerfile + configs)
├── tests/              ← Headless TUI tests, run by CI
├── docker/dev/         ← Local TUI test harness
└── docs/               ← Debugging notes and references
```

---

## 🔁 Termux and the container overlap

This is by design, and worth knowing before it confuses you. proot-distro binds
the Termux `$PREFIX` into the container at its original path and **appends**
`$PREFIX/bin` to the guest's `PATH`, so Termux's own binaries are reachable
from inside Debian.

Because the append puts Termux last, a tool present in both resolves to the
Debian copy. The Termux one only runs when Debian lacks the tool — which is
precisely when you would not expect it. `--shared-tmp` extends the same overlap
to `/tmp`: the container's `/tmp` *is* the Termux temp directory.

`Doctor → Dupes` lists tools installed on both sides and can uninstall the
Termux copies, on the assumption that the container is where you work. It only
offers packages the container is confirmed to provide, and it will not touch
anything XLabs itself needs — Python, git, proot-distro, Termux:X11,
PulseAudio or the graphics packages are not candidates.

---

## ⚠️ Limitations

| Limitation | Workaround |
|-----------|------------|
| No root | proot provides root-like environment |
| No systemd | Start services manually |
| No GPU passthrough | virgl renderer, software fallback |
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
