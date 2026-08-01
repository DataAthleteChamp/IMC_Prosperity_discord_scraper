"""CLI wiring: argument validation and the targets / ad-hoc branching.

These never reach the network — every case asserts on validation that happens
before a client is built.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from discord_channel_scraper.cli import main
from discord_channel_scraper.targets import EXAMPLE_CONFIG

CONFIG = """
[[targets]]
name = "alpha"
guild_id = "111111111111111111"
output_dir = "OUT/alpha"
channels = ["general"]

[[targets]]
name = "beta"
guild_id = "222222222222222222"
output_dir = "OUT/beta"
enabled = false
"""


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A developer's real .env / global config must not leak into these tests."""
    for var in ("DISCORD_GUILD_ID", "DISCORD_USER_TOKEN", "DISCORD_BOT_TOKEN", "SCRAPER_CONFIG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "scraper.toml"
    path.write_text(CONFIG.replace("OUT", str(tmp_path)))
    return path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_init_writes_a_config_and_refuses_to_clobber(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "scraper.toml").read_text() == EXAMPLE_CONFIG

    again = runner.invoke(main, ["init"])
    assert again.exit_code != 0
    assert "already exists" in again.output

    forced = runner.invoke(main, ["init", "--force"])
    assert forced.exit_code == 0, forced.output


def test_targets_lists_configured_servers(runner: CliRunner, config_path: Path) -> None:
    result = runner.invoke(main, ["targets", "--config", str(config_path), "--json"])
    assert result.exit_code == 0, result.output
    assert '"name": "alpha"' in result.output
    assert '"guild_id": "222222222222222222"' in result.output


def test_targets_without_a_config_explains_how_to_make_one(runner: CliRunner) -> None:
    result = runner.invoke(main, ["targets"])
    assert result.exit_code != 0
    assert "init" in result.output


def test_scrape_requires_an_explicit_choice_when_a_config_exists(
    runner: CliRunner, config_path: Path
) -> None:
    result = runner.invoke(main, ["scrape", "--config", str(config_path)])
    assert result.exit_code != 0
    assert "--target" in result.output
    assert "alpha" in result.output


def test_scrape_rejects_an_unknown_target(runner: CliRunner, config_path: Path) -> None:
    result = runner.invoke(main, ["scrape", "--config", str(config_path), "-t", "gamma"])
    assert result.exit_code != 0
    assert "No target named 'gamma'" in result.output


def test_scrape_rejects_guild_id_combined_with_targets(
    runner: CliRunner, config_path: Path
) -> None:
    result = runner.invoke(
        main, ["scrape", "--config", str(config_path), "--all", "--guild-id", "123"]
    )
    assert result.exit_code != 0
    assert "ad-hoc" in result.output


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--auth", "bot"),
        ("--channels", "general"),
        ("--exclude-channels", "spam"),
        ("--output-dir", "/tmp/elsewhere"),
    ],
)
def test_per_target_flags_are_rejected_rather_than_silently_ignored(
    runner: CliRunner, config_path: Path, flag: str, value: str
) -> None:
    result = runner.invoke(main, ["scrape", "--config", str(config_path), "--all", flag, value])
    assert result.exit_code != 0
    assert flag in result.output


def test_ad_hoc_run_requires_auth(runner: CliRunner) -> None:
    result = runner.invoke(main, ["scrape", "--guild-id", "123"])
    assert result.exit_code != 0
    assert "--auth is required" in result.output


def test_ad_hoc_run_requires_a_token(runner: CliRunner) -> None:
    result = runner.invoke(main, ["scrape", "--guild-id", "123", "--auth", "user"])
    assert result.exit_code != 0
    assert "DISCORD_USER_TOKEN is not set" in result.output


def test_missing_config_path_is_reported(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(main, ["scrape", "--config", str(tmp_path / "nope.toml"), "--all"])
    assert result.exit_code != 0
    assert "Config file not found" in result.output


def test_invalid_config_reports_the_problem_not_a_traceback(
    runner: CliRunner, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("[[targets]]\nname = 'a'\nguild_id = '1'\nrate_limit = 'fast'\n")
    result = runner.invoke(main, ["scrape", "--config", str(bad), "--all"])
    assert result.exit_code != 0
    assert "rate_limit must be a number" in result.output


def test_disabled_targets_are_skipped_by_all(runner: CliRunner, config_path: Path) -> None:
    """`--all` must not try to scrape `beta`, so the only failure is alpha's token."""
    result = runner.invoke(main, ["scrape", "--config", str(config_path), "--all"])
    assert result.exit_code != 0
    assert "1 target(s) failed: alpha" in result.output
