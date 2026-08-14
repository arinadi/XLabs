"""Claude Code MCP servers: entries in the container's ~/.claude.json
"mcpServers" block, loaded automatically by Claude Code in every project —
unlike providers.py's accounts, there is no separate activate step.

Same read-modify-write shape as providers.py: only the mcpServers key is
ever touched, everything else already in ~/.claude.json is read back and
written out unchanged.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from typing import Callable, NamedTuple

from .const import ADMIN_USER
from .system import container_path

Log = Callable[[str], None]

CLAUDE_JSON_REL = f"/home/{ADMIN_USER}/.claude.json"

VALID_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
SAFE_URL = re.compile(r"^https?://\S+$")

STDIO = "stdio"
HTTP = "http"
TYPES = (STDIO, HTTP)


class MCPServer(NamedTuple):
    name: str
    type: str  # "stdio" or "http"
    command: str = ""
    args: tuple[str, ...] = ()
    url: str = ""
    env: tuple[tuple[str, str], ...] = ()  # env for stdio, headers for http


def _noop_log(_: str) -> None:
    pass


def valid_server_name(name: str) -> bool:
    return bool(VALID_NAME.match(name))


def parse_args(text: str) -> tuple[list[str], str | None]:
    """Shell-style split so a quoted path with spaces survives. Returns the
    problem message instead of raising on an unbalanced quote."""
    try:
        return shlex.split(text), None
    except ValueError as e:
        return [], f"Args: {e}."


def parse_env(text: str) -> tuple[dict[str, str], list[str]]:
    """KEY=value per line; blank lines and lines starting with # are ignored."""
    env: dict[str, str] = {}
    problems: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            problems.append(f"Env/headers line {i}: expected KEY=value.")
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            problems.append(f"Env/headers line {i}: expected KEY=value.")
            continue
        env[key] = value.strip()
    return env, problems


def build_server(
    name: str, type_: str, command: str, args_text: str, url: str, env_text: str
) -> tuple[MCPServer | None, list[str]]:
    """Validates and parses a server in one pass — used by both the Add form
    and its tests, so the two can never disagree on what is well-formed."""
    problems: list[str] = []

    if not valid_server_name(name):
        problems.append(
            "Name: letters, digits, dot, underscore or dash only."
        )
    elif name in server_names():
        problems.append(f"Name: '{name}' is already added.")

    if type_ not in TYPES:
        problems.append("Type: must be stdio or http.")

    args: list[str] = []
    if type_ == STDIO:
        if not command.strip():
            problems.append("Command: required for a stdio server.")
        args, args_problem = parse_args(args_text)
        if args_problem:
            problems.append(args_problem)
    elif type_ == HTTP and not SAFE_URL.match(url.strip()):
        problems.append("URL: must start with http:// or https://, no spaces.")

    env, env_problems = parse_env(env_text)
    problems += env_problems

    if problems:
        return None, problems

    server = MCPServer(
        name=name,
        type=type_,
        command=command.strip(),
        args=tuple(args),
        url=url.strip(),
        env=tuple(sorted(env.items())),
    )
    return server, []


def _path() -> str:
    return container_path(CLAUDE_JSON_REL)


def _read(log: Log) -> tuple[dict, bool]:
    path = _path()
    if not os.path.exists(path):
        return {}, True
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        log(f"[red]Could not read {CLAUDE_JSON_REL}: {e}[/red]")
        return {}, False
    except json.JSONDecodeError as e:
        log(
            f"[red]{CLAUDE_JSON_REL} is not valid JSON ({e}) — fix it by "
            "hand before editing MCP servers.[/red]"
        )
        return {}, False
    if not isinstance(data, dict):
        log(f"[red]{CLAUDE_JSON_REL} does not contain a JSON object.[/red]")
        return {}, False
    return data, True


def _write(data: dict, log: Log) -> bool:
    path = _path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        return True
    except OSError as e:
        log(f"[red]Could not write {CLAUDE_JSON_REL}: {e}[/red]")
        return False


def list_servers() -> list[MCPServer]:
    data, ok = _read(_noop_log)
    if not ok:
        return []
    raw = data.get("mcpServers")
    if not isinstance(raw, dict):
        return []

    servers = []
    for name, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        type_ = cfg.get("type") or (STDIO if "command" in cfg else HTTP)
        env_map = cfg.get("headers") if type_ == HTTP else cfg.get("env")
        args = cfg.get("args") or []
        servers.append(
            MCPServer(
                name=name,
                type=type_,
                command=cfg.get("command", "") or "",
                args=tuple(args),
                url=cfg.get("url", "") or "",
                env=tuple(sorted((env_map or {}).items())),
            )
        )
    return sorted(servers, key=lambda s: s.name)


def server_names() -> list[str]:
    return [s.name for s in list_servers()]


def add_server(server: MCPServer, log: Log) -> bool:
    """Assumes build_server() already validated it."""
    data, ok = _read(log)
    if not ok:
        return False

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}

    if server.type == STDIO:
        cfg: dict = {"type": STDIO, "command": server.command}
        if server.args:
            cfg["args"] = list(server.args)
        if server.env:
            cfg["env"] = dict(server.env)
    else:
        cfg = {"type": HTTP, "url": server.url}
        if server.env:
            cfg["headers"] = dict(server.env)

    servers[server.name] = cfg
    data["mcpServers"] = servers
    if not _write(data, log):
        return False
    log(f"Added {server.name} to {CLAUDE_JSON_REL}.")
    return True


def remove_server(name: str, log: Log) -> bool:
    data, ok = _read(log)
    if not ok:
        return False

    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or name not in servers:
        return True

    del servers[name]
    if servers:
        data["mcpServers"] = servers
    else:
        data.pop("mcpServers", None)
    if not _write(data, log):
        return False
    log(f"Removed {name} from {CLAUDE_JSON_REL}.")
    return True
