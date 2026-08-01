"""Multi-target config parsing — synthetic configs only, no network."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from discord_channel_scraper.targets import (
    EXAMPLE_CONFIG,
    ConfigError,
    find_config,
    load_config,
)

TWO_SERVERS = """
[defaults]
auth = "user"
rate_limit = 4
output_dir = "./archive"

[[targets]]
name = "alpha"
guild_id = "111111111111111111"
channels = ["general", "222222222222222222"]

[[targets]]
name = "beta"
guild_id = "333333333333333333"
output_dir = "/tmp/beta-archive"
exclude_channels = ["off-topic"]
auth = "bot"
token_env = "DISCORD_BOT_TOKEN_BETA"
since = "2025-01-01T00:00:00Z"
enabled = false
"""


def _write(tmp_path: Path, body: str, name: str = "scraper.toml") -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_loads_two_servers_with_separate_output_dirs(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, TWO_SERVERS))

    alpha, beta = cfg.targets
    assert alpha.name == "alpha"
    assert alpha.guild_id == "111111111111111111"
    assert alpha.channels == ("general", "222222222222222222")
    assert alpha.auth_mode == "user"
    assert alpha.rate_limit == 4
    # No explicit output_dir -> subdirectory of the [defaults] base.
    assert alpha.output_dir == (tmp_path / "archive" / "alpha").resolve()
    assert alpha.resolved_token_env == "DISCORD_USER_TOKEN"

    assert beta.output_dir == Path("/tmp/beta-archive").resolve()
    assert beta.auth_mode == "bot"
    assert beta.resolved_token_env == "DISCORD_BOT_TOKEN_BETA"
    assert beta.exclude_channels == ("off-topic",)
    assert beta.since == datetime(2025, 1, 1, tzinfo=UTC)
    assert beta.enabled is False


def test_select_by_name_and_enabled_only(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, TWO_SERVERS))

    assert [t.name for t in cfg.select(["beta"])] == ["beta"]
    assert [t.name for t in cfg.select(None)] == ["alpha"]  # beta is disabled

    with pytest.raises(ConfigError, match="No target named 'gamma'"):
        cfg.select(["gamma"])


def test_relative_output_dir_is_anchored_at_the_config_file(tmp_path: Path) -> None:
    nested = tmp_path / "conf"
    nested.mkdir()
    body = """
[[targets]]
name = "a"
guild_id = "1"
output_dir = "out"
"""
    cfg = load_config(_write(nested, body))
    assert cfg.targets[0].output_dir == (nested / "out").resolve()


def test_user_home_and_env_vars_expand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_ARCHIVE_ROOT", "/tmp/root")
    body = """
[[targets]]
name = "a"
guild_id = "1"
output_dir = "$MY_ARCHIVE_ROOT/a"

[[targets]]
name = "b"
guild_id = "2"
output_dir = "~/b"
"""
    cfg = load_config(_write(tmp_path, body))
    assert cfg.targets[0].output_dir == Path("/tmp/root/a").resolve()
    assert cfg.targets[1].output_dir == (Path.home() / "b").resolve()


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("[[targets]]\nguild_id = '1'\n", "needs a 'name'"),
        ("[[targets]]\nname = 'a'\n", "missing 'guild_id'"),
        ("[[targets]]\nname = 'a'\nguild_id = 'not-a-number'\n", "must be numeric"),
        ("[[targets]]\nname = 'a'\nguild_id = '1'\nauth = 'browser'\n", "auth must be"),
        ("[defaults]\nauth = 'user'\n", "no \\[\\[targets\\]\\] entries"),
        (
            "[[targets]]\nname = 'a'\nguild_id = '1'\nchannels = 'general'\nsince = 'nope'\n",
            "not a valid ISO-8601",
        ),
        ("[[targets]]\nname = 'a'\nguild_id = '1'\ntypo = 1\n", "unknown key"),
    ],
)
def test_invalid_configs_are_rejected(tmp_path: Path, body: str, match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        load_config(_write(tmp_path, body))


def test_duplicate_names_are_rejected(tmp_path: Path) -> None:
    body = """
[[targets]]
name = "a"
guild_id = "1"
output_dir = "/tmp/one"

[[targets]]
name = "a"
guild_id = "2"
output_dir = "/tmp/two"
"""
    with pytest.raises(ConfigError, match="duplicate target name"):
        load_config(_write(tmp_path, body))


def test_shared_output_dir_is_rejected(tmp_path: Path) -> None:
    """Two targets in one directory would clobber each other's _cursors.json."""
    body = """
[[targets]]
name = "a"
guild_id = "1"
output_dir = "/tmp/shared"

[[targets]]
name = "b"
guild_id = "2"
output_dir = "/tmp/shared"
"""
    with pytest.raises(ConfigError, match="same output_dir"):
        load_config(_write(tmp_path, body))


def test_case_only_different_names_collide_on_case_insensitive_filesystems(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "CaseProbe"
    probe.mkdir()
    if not (tmp_path / "caseprobe").exists():
        pytest.skip("case-sensitive filesystem")
    body = """
[[targets]]
name = "Alpha"
guild_id = "1"

[[targets]]
name = "alpha"
guild_id = "2"
"""
    with pytest.raises(ConfigError, match="same output_dir"):
        load_config(_write(tmp_path, body))


@pytest.mark.parametrize("name", ["alpha/../beta", "/tmp/escaped", "a/b", "..", "."])
def test_names_cannot_escape_the_base_output_dir(tmp_path: Path, name: str) -> None:
    body = f"[[targets]]\nname = '{name}'\nguild_id = '1'\n"
    with pytest.raises(ConfigError, match=r"path separators|needs a 'name'"):
        load_config(_write(tmp_path, body))


@pytest.mark.parametrize("value", ['"fast"', "[1]", "0", "-3", "true"])
def test_bad_rate_limit_is_a_config_error_not_a_traceback(tmp_path: Path, value: str) -> None:
    body = f"[[targets]]\nname = 'a'\nguild_id = '1'\nrate_limit = {value}\n"
    with pytest.raises(ConfigError, match="rate_limit must be"):
        load_config(_write(tmp_path, body))


def test_bad_rate_limit_in_defaults_is_also_caught(tmp_path: Path) -> None:
    body = "[defaults]\nrate_limit = 'fast'\n\n[[targets]]\nname = 'a'\nguild_id = '1'\n"
    with pytest.raises(ConfigError, match="rate_limit must be"):
        load_config(_write(tmp_path, body))


def test_single_channel_string_is_accepted_as_a_list(tmp_path: Path) -> None:
    body = "[[targets]]\nname = 'a'\nguild_id = '1'\nchannels = 'general'\n"
    assert load_config(_write(tmp_path, body)).targets[0].channels == ("general",)


def test_find_config_prefers_explicit_then_env_then_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = _write(tmp_path, TWO_SERVERS, "explicit.toml")
    from_env = _write(tmp_path, TWO_SERVERS, "from-env.toml")
    in_cwd = _write(tmp_path, TWO_SERVERS)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SCRAPER_CONFIG", str(from_env))

    assert find_config(explicit) == explicit
    assert find_config(None) == from_env
    monkeypatch.delenv("SCRAPER_CONFIG")
    assert find_config(None) == in_cwd


def test_find_config_reports_missing_paths(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        find_config(tmp_path / "nope.toml")


def test_shipped_example_config_is_valid(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, EXAMPLE_CONFIG))
    assert [t.name for t in cfg.targets] == ["server-one", "server-two"]


def test_example_toml_file_matches_the_embedded_template() -> None:
    shipped = Path(__file__).resolve().parents[1] / "scraper.example.toml"
    assert shipped.read_text(encoding="utf-8") == EXAMPLE_CONFIG
