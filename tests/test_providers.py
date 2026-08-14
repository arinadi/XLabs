"""installer/providers.py: saved Claude Code accounts and switching between
them inside the container's ~/.claude/settings.json.

    python tests/test_providers.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from installer import providers


def _isolated(test):
    """Point container_path at a tempdir and clear any saved provider state
    before the test, restoring both afterwards — the same shape
    test_packages.py uses for anything that touches the container or .env.
    """

    def wrapper() -> None:
        from installer import config

        fake_root = tempfile.mkdtemp()
        original_container_path = providers.container_path
        providers.container_path = lambda p: os.path.join(fake_root, p.lstrip("/"))

        original = {
            k: config.get(k)
            for k in (providers.NAMES_KEY, providers.ACTIVE_KEY)
        }
        for name in list(providers.provider_names()):
            providers.remove_provider(name)

        try:
            test(fake_root)
        finally:
            providers.container_path = original_container_path
            for name in list(providers.provider_names()):
                providers.remove_provider(name)
            for key, value in original.items():
                if value is None:
                    config.unset(key)
                else:
                    config.set_value(key, value)

    wrapper.__name__ = test.__name__
    return wrapper


@_isolated
def test_validate_provider(fake_root: str) -> None:
    check(
        providers.validate_provider("work", "https://gw.example.com", "tok-1") == [],
        "a well-formed provider was rejected",
    )
    check(
        providers.validate_provider("official", "https://gw.example.com", "tok") != [],
        "the reserved name 'official' was accepted",
    )
    check(
        providers.validate_provider("bad name!", "https://gw.example.com", "tok") != [],
        "a name with spaces/punctuation was accepted",
    )
    check(
        providers.validate_provider("work", "not-a-url", "tok") != [],
        "a base URL without a scheme was accepted",
    )
    check(
        providers.validate_provider("work", "https://gw.example.com", "") != [],
        "an empty token was accepted",
    )
    check(
        providers.validate_provider("work", "https://gw.example.com", "tok\nEVIL=1") != [],
        "a token containing a newline was accepted",
    )

    check(
        providers.add_provider(providers.Provider("work", "https://gw.example.com", "tok-1")),
        "could not save the first provider",
    )
    check(
        providers.validate_provider("work", "https://other.example.com", "tok-2") != [],
        "adding a second provider under an already-used name was accepted",
    )


@_isolated
def test_provider_roundtrip(fake_root: str) -> None:
    p = providers.Provider(
        name="work",
        base_url="https://gw.example.com",
        auth_token="tok-1",
        opus_model="big",
        sonnet_model="mid",
        haiku_model="small",
    )
    check(providers.add_provider(p), "could not save the provider")
    check(providers.provider_names() == ["work"], "provider not listed after adding")
    check(providers.provider_by_name("work") == p, "provider did not round-trip")

    check(providers.remove_provider("work"), "could not remove the provider")
    check(providers.provider_names() == [], "provider still listed after removal")
    check(providers.provider_by_name("work") is None, "removed provider still readable")


@_isolated
def test_activate_writes_and_clears_env(fake_root: str) -> None:
    """activate() must only touch the ANTHROPIC_* keys it owns, leaving any
    hand-added settings.json content — permission rules here — alone."""
    settings_path = os.path.join(fake_root, "home", "admin", ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings_path))
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump({"permissions": {"allow": ["Bash(git status)"]}}, f)

    lines: list[str] = []
    p = providers.Provider("work", "https://gw.example.com", "tok-1", opus_model="big")
    check(providers.add_provider(p), "could not save the provider")

    check(providers.activate("work", lines.append), "activation reported failure")
    check(providers.active_provider_name() == "work", "active provider was not saved")

    with open(settings_path, encoding="utf-8") as f:
        written = json.load(f)
    check(
        written["permissions"]["allow"] == ["Bash(git status)"],
        "activate() disturbed an unrelated settings.json key",
    )
    check(written["env"]["ANTHROPIC_BASE_URL"] == "https://gw.example.com", "base URL not written")
    check(written["env"]["ANTHROPIC_AUTH_TOKEN"] == "tok-1", "auth token not written")
    check(written["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "big", "opus override not written")
    check("ANTHROPIC_DEFAULT_SONNET_MODEL" not in written["env"], "unset override was written anyway")

    check(providers.activate(providers.OFFICIAL, lines.append), "switching back to official failed")
    check(providers.active_provider_name() == providers.OFFICIAL, "active provider not reset")

    with open(settings_path, encoding="utf-8") as f:
        written = json.load(f)
    check("env" not in written, "official activation left gateway keys behind")
    check(
        written["permissions"]["allow"] == ["Bash(git status)"],
        "switching back to official disturbed an unrelated settings.json key",
    )


@_isolated
def test_activate_refuses_corrupt_settings(fake_root: str) -> None:
    """A settings.json that fails to parse must abort the switch rather than
    be silently replaced — the file may hold hand-edited content worth
    more than a clean overwrite."""
    settings_path = os.path.join(fake_root, "home", "admin", ".claude", "settings.json")
    os.makedirs(os.path.dirname(settings_path))
    with open(settings_path, "w", encoding="utf-8") as f:
        f.write("{ not valid json")

    p = providers.Provider("work", "https://gw.example.com", "tok-1")
    check(providers.add_provider(p), "could not save the provider")

    lines: list[str] = []
    check(not providers.activate("work", lines.append), "activation succeeded against broken JSON")
    check(any("not valid JSON" in line for line in lines), f"no parse error logged: {lines}")

    with open(settings_path, encoding="utf-8") as f:
        check(f.read() == "{ not valid json", "the broken file was overwritten anyway")


TESTS = [
    test_validate_provider,
    test_provider_roundtrip,
    test_activate_writes_and_clears_env,
    test_activate_refuses_corrupt_settings,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
