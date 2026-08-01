"""Multi-server configuration: named scrape *targets* loaded from TOML.

One target = one Discord server (guild) + which channels to take from it +
where its output goes. Two targets can share the same account token, which is
the common case: one Discord account that is a member of several servers.

Example ``scraper.toml``::

    [defaults]
    auth = "user"
    rate_limit = 5
    output_dir = "./data"

    [[targets]]
    name = "prosperity"
    guild_id = "1234567890123456789"
    output_dir = "/Users/me/archives/prosperity"
    channels = ["general", "round-5", "333333333333333333"]

    [[targets]]
    name = "other-comp"
    guild_id = "9876543210987654321"
    output_dir = "/Users/me/archives/other-comp"
    exclude_channels = ["off-topic"]

Parsing uses the standard library :mod:`tomllib` (Python 3.11+), so enabling
multi-server support adds no third-party dependency.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

AuthMode = Literal["bot", "user"]

DEFAULT_CONFIG_NAME = "scraper.toml"
CONFIG_ENV_VAR = "SCRAPER_CONFIG"

#: Fallback token env var per auth mode, when a target sets no ``token_env``.
DEFAULT_TOKEN_ENV: dict[str, str] = {
    "bot": "DISCORD_BOT_TOKEN",
    "user": "DISCORD_USER_TOKEN",
}

_TARGET_KEYS = {
    "name",
    "guild_id",
    "output_dir",
    "channels",
    "exclude_channels",
    "since",
    "until",
    "auth",
    "token_env",
    "rate_limit",
    "enabled",
}
_DEFAULTS_KEYS = {"auth", "token_env", "rate_limit", "output_dir", "since", "until"}

EXAMPLE_CONFIG = """\
# =============================================================================
# discord-channel-scraper — scrape targets
#
# One [[targets]] block per Discord server. Tokens NEVER go in this file; they
# live in .env / the environment, so this file is safe to share or commit.
# Find IDs with Developer Mode on: right-click a server or channel -> Copy ID.
# =============================================================================

[defaults]
auth = "user"          # "user" (your account token) or "bot" (invited bot token)
rate_limit = 5         # average requests/second; keep <= 10
output_dir = "./data"  # base dir for targets that don't set their own

[[targets]]
name = "server-one"
guild_id = "000000000000000000"
# Absolute path is recommended so output doesn't depend on where you run from.
output_dir = "/absolute/path/to/server-one"
# Channels to scrape, by name or ID. Omit or leave empty for every readable
# channel. Naming a forum/text channel also includes its threads.
channels = ["general", "announcements"]
exclude_channels = []
# since = "2025-01-01T00:00:00Z"
# until = "2025-12-31T23:59:59Z"

[[targets]]
name = "server-two"
guild_id = "111111111111111111"
output_dir = "/absolute/path/to/server-two"
channels = ["strategy", "333333333333333333"]
exclude_channels = ["off-topic"]
# enabled = false                        # skip this target in `scrape --all`
# token_env = "DISCORD_USER_TOKEN_ALT"   # use a different account for this server
"""


class ConfigError(RuntimeError):
    """Raised when a config file is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class Target:
    """A single server to scrape, with its own filters and output location."""

    name: str
    guild_id: str
    output_dir: Path
    auth_mode: AuthMode = "user"
    token_env: str | None = None
    channels: tuple[str, ...] = ()
    exclude_channels: tuple[str, ...] = ()
    since: datetime | None = None
    until: datetime | None = None
    rate_limit: float | None = None
    enabled: bool = True

    @property
    def resolved_token_env(self) -> str:
        return self.token_env or DEFAULT_TOKEN_ENV[self.auth_mode]


@dataclass(frozen=True)
class ScraperConfig:
    """A parsed config file: its path plus the targets it declares."""

    path: Path
    targets: tuple[Target, ...] = field(default_factory=tuple)

    def get(self, name: str) -> Target:
        for t in self.targets:
            if t.name == name:
                return t
        known = ", ".join(t.name for t in self.targets) or "<none>"
        raise ConfigError(f"No target named {name!r} in {self.path}. Known targets: {known}")

    def select(self, names: list[str] | tuple[str, ...] | None) -> list[Target]:
        """Return targets by name, or every enabled target when ``names`` is empty."""
        if names:
            return [self.get(n) for n in names]
        return [t for t in self.targets if t.enabled]


def find_config(explicit: Path | str | None = None) -> Path | None:
    """Locate a config file.

    Search order: explicit path, ``$SCRAPER_CONFIG``, ``./scraper.toml``,
    ``~/.config/discord-channel-scraper/config.toml``.
    """
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        return path

    env_path = os.environ.get(CONFIG_ENV_VAR, "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if not path.exists():
            raise ConfigError(f"{CONFIG_ENV_VAR} points at a missing file: {path}")
        return path

    for candidate in (
        Path.cwd() / DEFAULT_CONFIG_NAME,
        Path.home() / ".config" / "discord-channel-scraper" / "config.toml",
    ):
        if candidate.exists():
            return candidate
    return None


def load_config(path: Path | str) -> ScraperConfig:
    """Parse and validate a targets config file."""
    path = Path(path).expanduser().resolve()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} is not valid TOML: {e}") from e
    except OSError as e:
        raise ConfigError(f"Cannot read {path}: {e}") from e

    defaults = raw.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ConfigError(f"{path}: [defaults] must be a table")
    _reject_unknown(defaults, _DEFAULTS_KEYS, f"{path}: [defaults]")

    raw_targets = raw.get("targets")
    if raw_targets is None:
        raise ConfigError(f"{path}: no [[targets]] entries found")
    if not isinstance(raw_targets, list):
        raise ConfigError(f"{path}: 'targets' must be an array of tables ([[targets]])")

    base_dir = _resolve_dir(defaults.get("output_dir", "./data"), path.parent)

    targets: list[Target] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw_targets):
        if not isinstance(entry, dict):
            raise ConfigError(f"{path}: [[targets]] #{i + 1} must be a table")
        target = _parse_target(entry, defaults=defaults, base_dir=base_dir, config_path=path)
        if target.name in seen:
            raise ConfigError(f"{path}: duplicate target name {target.name!r}")
        seen.add(target.name)
        targets.append(target)

    _reject_output_collisions(targets, path)
    return ScraperConfig(path=path, targets=tuple(targets))


def _parse_target(
    entry: dict[str, Any],
    *,
    defaults: dict[str, Any],
    base_dir: Path,
    config_path: Path,
) -> Target:
    name = str(entry.get("name") or "").strip()
    if not name:
        raise ConfigError(f"{config_path}: every [[targets]] entry needs a 'name'")
    where = f"{config_path}: target {name!r}"
    # The name becomes a directory component under [defaults].output_dir, so it
    # must not be able to escape it or alias another target's directory.
    if set(name) & {"/", "\\", os.sep} or name in (".", ".."):
        raise ConfigError(f"{where}: name must not contain path separators")
    _reject_unknown(entry, _TARGET_KEYS, where)

    guild_id = str(entry.get("guild_id") or "").strip()
    if not guild_id:
        raise ConfigError(f"{where} is missing 'guild_id'")
    if not guild_id.isdigit():
        raise ConfigError(f"{where}: guild_id must be numeric, got {guild_id!r}")

    auth_mode = str(entry.get("auth") or defaults.get("auth") or "user").strip()
    if auth_mode not in ("bot", "user"):
        raise ConfigError(f"{where}: auth must be 'bot' or 'user', got {auth_mode!r}")

    # An explicit per-target output_dir wins; otherwise the target gets its own
    # subdirectory under the shared base so two servers never share cursors.
    raw_out = entry.get("output_dir")
    output_dir = (
        _resolve_dir(raw_out, config_path.parent) if raw_out else (base_dir / name).resolve()
    )

    rate_limit = _parse_rate_limit(entry.get("rate_limit", defaults.get("rate_limit")), where)
    return Target(
        name=name,
        guild_id=guild_id,
        output_dir=output_dir,
        auth_mode=auth_mode,  # type: ignore[arg-type]
        token_env=(entry.get("token_env") or defaults.get("token_env") or None),
        channels=_str_tuple(entry.get("channels"), f"{where}: channels"),
        exclude_channels=_str_tuple(entry.get("exclude_channels"), f"{where}: exclude_channels"),
        since=_parse_dt(entry.get("since", defaults.get("since")), f"{where}: since"),
        until=_parse_dt(entry.get("until", defaults.get("until")), f"{where}: until"),
        rate_limit=rate_limit,
        enabled=bool(entry.get("enabled", True)),
    )


def _parse_rate_limit(value: Any, where: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ConfigError(f"{where}: rate_limit must be a number, got {value!r}")
    try:
        rate = float(value)
    except (TypeError, ValueError) as e:
        raise ConfigError(f"{where}: rate_limit must be a number, got {value!r}") from e
    if rate <= 0:
        raise ConfigError(f"{where}: rate_limit must be greater than 0, got {rate}")
    return rate


def _resolve_dir(value: Any, relative_to: Path) -> Path:
    """Expand ``~``/``$VARS`` and anchor relative paths at the config file."""
    path = Path(os.path.expandvars(str(value))).expanduser()
    if not path.is_absolute():
        path = relative_to / path
    return path.resolve()


def _str_tuple(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ConfigError(f"{where} must be a list of strings")
    return tuple(str(v).strip() for v in value if str(v).strip())


def _parse_dt(value: Any, where: str) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as e:
        raise ConfigError(f"{where} is not a valid ISO-8601 timestamp: {value!r}") from e


def _reject_unknown(entry: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise ConfigError(
            f"{where}: unknown key(s) {', '.join(unknown)}. Allowed: {', '.join(sorted(allowed))}"
        )


def _reject_output_collisions(targets: list[Target], path: Path) -> None:
    """Two targets writing to one directory would corrupt each other's cursors."""
    by_dir: dict[str, str] = {}
    for t in targets:
        # Case-folded, because macOS and Windows filesystems are case-insensitive
        # by default (``os.path.normcase`` is a no-op on POSIX, so it can't be
        # relied on here). Two paths differing only in case are always a mistake.
        key = os.path.normcase(str(t.output_dir)).casefold()
        clash = by_dir.get(key)
        if clash:
            raise ConfigError(
                f"{path}: targets {clash!r} and {t.name!r} resolve to the same output_dir "
                f"{t.output_dir} (compared case-insensitively) — "
                f"give each target its own directory"
            )
        by_dir[key] = t.name
