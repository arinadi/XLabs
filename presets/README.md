# Presets

Drop a `.tar.gz` from the **Backup** screen here (same format the app
already writes to `~/XLabs-backups` — this is just a second, repo-tracked
location for one you want carried across installs). Commit it, and:

- **Start → Install** (first pull, no container yet) restores it
  automatically, unconditionally.
- **Doctor → Fix** restores it automatically when it has to pull a missing
  container back.
- **Reset** shows a checkbox — on by default — to restore it after wiping
  and reinstalling, so a deliberately clean reset is still one tap away.

If more than one `.tar.gz` ends up here, the newest by modification time
wins; the rest are ignored, not merged.

This is your desktop config (dotfiles, panel layout, window manager theme,
editor settings, the Firefox profile) — not a copy XLabs maintains or
updates on its own. See [`installer/presets.py`](../installer/presets.py)
and [`installer/backup.py`](../installer/backup.py) for how it's applied.
