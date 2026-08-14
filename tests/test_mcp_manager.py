"""installer/mcp_manager.py: MCP servers saved in the container's
~/.claude.json "mcpServers" block.

    python tests/test_mcp_manager.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from installer import mcp_manager


def _isolated(test):
    """Point container_path at a tempdir, the same shape test_providers.py
    uses for anything that touches the container."""

    def wrapper() -> None:
        fake_root = tempfile.mkdtemp()
        original_container_path = mcp_manager.container_path
        mcp_manager.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))
        try:
            test(fake_root)
        finally:
            mcp_manager.container_path = original_container_path

    wrapper.__name__ = test.__name__
    return wrapper


@_isolated
def test_build_server_stdio(fake_root: str) -> None:
    server, problems = mcp_manager.build_server(
        "fs", "stdio", "npx", "-y @scope/server '/a path/with space'", "", "FOO=bar\n# comment\n"
    )
    check(problems == [], f"a well-formed stdio server was rejected: {problems}")
    check(server is not None, "no server returned despite no problems")
    check(server.command == "npx", "command not parsed")
    check(server.args == ("-y", "@scope/server", "/a path/with space"), f"args not split: {server.args}")
    check(server.env == (("FOO", "bar"),), f"env not parsed: {server.env}")


@_isolated
def test_build_server_rejects_bad_input(fake_root: str) -> None:
    _, problems = mcp_manager.build_server("bad name!", "stdio", "npx", "", "", "")
    check(problems != [], "a name with spaces/punctuation was accepted")

    _, problems = mcp_manager.build_server("fs", "stdio", "", "", "", "")
    check(problems != [], "a stdio server with no command was accepted")

    _, problems = mcp_manager.build_server("remote", "http", "", "", "not-a-url", "")
    check(problems != [], "an http server with a bad URL was accepted")

    _, problems = mcp_manager.build_server("fs", "stdio", "npx", "'unterminated", "", "")
    check(problems != [], "unbalanced quoting in args was accepted")

    _, problems = mcp_manager.build_server("fs", "stdio", "npx", "", "", "not-key-value")
    check(problems != [], "an env line without '=' was accepted")


@_isolated
def test_add_list_remove_roundtrip(fake_root: str) -> None:
    lines: list[str] = []
    stdio, problems = mcp_manager.build_server("fs", "stdio", "npx", "-y server", "", "")
    check(problems == [], f"unexpected problems: {problems}")
    check(mcp_manager.add_server(stdio, lines.append), "could not add the stdio server")

    http, problems = mcp_manager.build_server(
        "remote", "http", "", "", "https://mcp.example.com/sse", "Authorization=Bearer tok"
    )
    check(problems == [], f"unexpected problems: {problems}")
    check(mcp_manager.add_server(http, lines.append), "could not add the http server")

    names = mcp_manager.server_names()
    check(names == ["fs", "remote"], f"servers not listed in name order: {names}")

    servers = {s.name: s for s in mcp_manager.list_servers()}
    check(servers["fs"] == stdio, "stdio server did not round-trip")
    check(servers["remote"] == http, "http server did not round-trip")

    check(mcp_manager.remove_server("fs", lines.append), "could not remove fs")
    check(mcp_manager.server_names() == ["remote"], "fs still listed after removal")

    check(mcp_manager.remove_server("remote", lines.append), "could not remove remote")
    check(mcp_manager.server_names() == [], "remote still listed after removal")

    # An empty mcpServers block should not be left behind as clutter.
    path = os.path.join(fake_root, "home", "admin", ".claude.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    check("mcpServers" not in data, "an empty mcpServers block was left in the file")


@_isolated
def test_add_preserves_unrelated_keys(fake_root: str) -> None:
    """add_server()/remove_server() must only touch mcpServers, leaving
    everything else already in ~/.claude.json alone."""
    path = os.path.join(fake_root, "home", "admin", ".claude.json")
    os.makedirs(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"numStartups": 12, "theme": "dark"}, f)

    lines: list[str] = []
    server, problems = mcp_manager.build_server("fs", "stdio", "npx", "", "", "")
    check(problems == [], f"unexpected problems: {problems}")
    check(mcp_manager.add_server(server, lines.append), "could not add the server")

    with open(path, encoding="utf-8") as f:
        written = json.load(f)
    check(written["numStartups"] == 12, "add_server() disturbed an unrelated key")
    check(written["theme"] == "dark", "add_server() disturbed an unrelated key")
    check("fs" in written["mcpServers"], "server not written")


@_isolated
def test_read_refuses_corrupt_json(fake_root: str) -> None:
    path = os.path.join(fake_root, "home", "admin", ".claude.json")
    os.makedirs(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ not valid json")

    check(mcp_manager.list_servers() == [], "list_servers() did not fail closed on bad JSON")

    lines: list[str] = []
    server, problems = mcp_manager.build_server("fs", "stdio", "npx", "", "", "")
    check(problems == [], f"unexpected problems: {problems}")
    check(not mcp_manager.add_server(server, lines.append), "add succeeded against broken JSON")
    check(any("not valid JSON" in line for line in lines), f"no parse error logged: {lines}")

    with open(path, encoding="utf-8") as f:
        check(f.read() == "{ not valid json", "the broken file was overwritten anyway")


TESTS = [
    test_build_server_stdio,
    test_build_server_rejects_bad_input,
    test_add_list_remove_roundtrip,
    test_add_preserves_unrelated_keys,
    test_read_refuses_corrupt_json,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
