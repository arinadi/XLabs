"""Claude Code provider profiles: which account Claude Code authenticates
against inside the container.

Profiles (name, base URL, token, optional model overrides) are stored in
.env via config.py, the same pattern audio.py/bench.py/isolation.py use for
their own settings — each key namespaced under CLAUDE_PROVIDER_<NAME>_ so it
survives alongside every other module's keys in the same flat file.

Only the active profile is ever written into the container: activate()
regenerates the ANTHROPIC_* keys this module owns inside
~/.claude/settings.json's "env" block, or clears them entirely to fall back
to the official claude.ai / Anthropic Console login. Every other key already
in that file — permission rules, hooks, anything set by hand — is left
alone.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, NamedTuple

from . import config
from .const import ADMIN_USER
from .system import container_path

Log = Callable[[str], None]

CLAUDE_SETTINGS_REL = f"/home/{ADMIN_USER}/.claude/settings.json"

NAMES_KEY = "CLAUDE_PROVIDERS"
ACTIVE_KEY = "CLAUDE_ACTIVE_PROVIDER"

# Reserved: not a saved profile, just the "no gateway" state.
OFFICIAL = "official"

VALID_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,31}$")
SAFE_URL = re.compile(r"^https?://\S+$")

# The only keys activate() ever writes or clears — never touch anything else
# already present in the container's settings.json.
_MANAGED_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
)


class Provider(NamedTuple):
    name: str
    base_url: str
    auth_token: str
    opus_model: str = ""
    sonnet_model: str = ""
    haiku_model: str = ""


def _prefix(name: str) -> str:
    return f"CLAUDE_PROVIDER_{name.upper()}_"


def valid_provider_name(name: str) -> bool:
    return bool(VALID_NAME.match(name)) and name.lower() != OFFICIAL


def validate_provider(name: str, base_url: str, auth_token: str) -> list[str]:
    """Field-by-field problems, or an empty list when the provider can be added."""
    problems = []

    if not valid_provider_name(name):
        problems.append(
            "Name: letters, digits, dot, underscore or dash only, and not 'official'."
        )
    elif name in provider_names():
        problems.append(f"Name: '{name}' is already added.")

    if not SAFE_URL.match(base_url.strip()):
        problems.append("Base URL: must start with http:// or https://, no spaces.")

    # A newline would break the one-key-per-line .env format this is stored
    # in, corrupting every key written after it — not just this one.
    if not auth_token.strip():
        problems.append("Auth token: required.")
    elif "\n" in auth_token or "\r" in auth_token:
        problems.append("Auth token: must be a single line.")

    return problems


def provider_names() -> list[str]:
    raw = config.get(NAMES_KEY, "") or ""
    return [n for n in raw.split(",") if n]


def provider_by_name(name: str) -> Provider | None:
    if name not in provider_names():
        return None
    prefix = _prefix(name)
    base_url = config.get(f"{prefix}BASE_URL")
    auth_token = config.get(f"{prefix}AUTH_TOKEN")
    if not base_url or not auth_token:
        return None
    return Provider(
        name=name,
        base_url=base_url,
        auth_token=auth_token,
        opus_model=config.get(f"{prefix}OPUS_MODEL", "") or "",
        sonnet_model=config.get(f"{prefix}SONNET_MODEL", "") or "",
        haiku_model=config.get(f"{prefix}HAIKU_MODEL", "") or "",
    )


def list_providers() -> list[Provider]:
    return [p for p in (provider_by_name(n) for n in provider_names()) if p is not None]


def add_provider(provider: Provider) -> bool:
    """Assumes validate_provider() already passed."""
    prefix = _prefix(provider.name)
    ok = config.set_value(f"{prefix}BASE_URL", provider.base_url)
    ok = config.set_value(f"{prefix}AUTH_TOKEN", provider.auth_token) and ok
    for field, value in (
        ("OPUS_MODEL", provider.opus_model),
        ("SONNET_MODEL", provider.sonnet_model),
        ("HAIKU_MODEL", provider.haiku_model),
    ):
        if value:
            ok = config.set_value(f"{prefix}{field}", value) and ok

    names = provider_names()
    if provider.name not in names:
        names.append(provider.name)
        ok = config.set_value(NAMES_KEY, ",".join(names)) and ok
    return ok


def remove_provider(name: str) -> bool:
    prefix = _prefix(name)
    for field in ("BASE_URL", "AUTH_TOKEN", "OPUS_MODEL", "SONNET_MODEL", "HAIKU_MODEL"):
        config.unset(f"{prefix}{field}")

    names = [n for n in provider_names() if n != name]
    ok = config.set_value(NAMES_KEY, ",".join(names))
    if active_provider_name() == name:
        config.unset(ACTIVE_KEY)
    return ok


def active_provider_name() -> str:
    return config.get(ACTIVE_KEY, OFFICIAL) or OFFICIAL


def _settings_path() -> str:
    return container_path(CLAUDE_SETTINGS_REL)


def _read_settings(log: Log) -> tuple[dict, bool]:
    path = _settings_path()
    if not os.path.exists(path):
        return {}, True
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        log(f"[red]Could not read {CLAUDE_SETTINGS_REL}: {e}[/red]")
        return {}, False
    except json.JSONDecodeError as e:
        log(
            f"[red]{CLAUDE_SETTINGS_REL} is not valid JSON ({e}) — fix it by "
            "hand before switching providers.[/red]"
        )
        return {}, False
    if not isinstance(data, dict):
        log(f"[red]{CLAUDE_SETTINGS_REL} does not contain a JSON object.[/red]")
        return {}, False
    return data, True


def _write_settings(settings: dict, log: Log) -> bool:
    path = _settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        return True
    except OSError as e:
        log(f"[red]Could not write {CLAUDE_SETTINGS_REL}: {e}[/red]")
        return False


def activate(name: str, log: Log) -> bool:
    """Switch Claude Code inside the container to `name` (or OFFICIAL).

    Rewrites only the ANTHROPIC_* keys this module owns in the container's
    ~/.claude/settings.json "env" block — everything else already in that
    file is read back and written out unchanged.
    """
    if name != OFFICIAL and name not in provider_names():
        log(f"[red]Unknown provider: {name}[/red]")
        return False

    settings, ok = _read_settings(log)
    if not ok:
        return False

    env = settings.get("env")
    if not isinstance(env, dict):
        env = {}

    for key in _MANAGED_ENV_KEYS:
        env.pop(key, None)

    if name != OFFICIAL:
        provider = provider_by_name(name)
        if provider is None:
            log(f"[red]{name} has no saved base URL/token.[/red]")
            return False
        env["ANTHROPIC_BASE_URL"] = provider.base_url
        env["ANTHROPIC_AUTH_TOKEN"] = provider.auth_token
        if provider.opus_model:
            env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = provider.opus_model
        if provider.sonnet_model:
            env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = provider.sonnet_model
        if provider.haiku_model:
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = provider.haiku_model

    if env:
        settings["env"] = env
    else:
        settings.pop("env", None)

    if not _write_settings(settings, log):
        return False

    if not config.set_value(ACTIVE_KEY, name):
        log("[red]Wrote settings.json but could not save the active provider.[/red]")
        return False

    label = "Official" if name == OFFICIAL else name
    log(f"Active provider: {label}. {CLAUDE_SETTINGS_REL} updated.")
    return True
