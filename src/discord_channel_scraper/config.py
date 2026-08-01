"""Runtime configuration loaded from environment.

Secrets (tokens) always live in the environment or ``.env`` — never in the
targets config file, which is meant to be safe to share. Everything about
*what* to scrape lives in ``scraper.toml``; see :mod:`.targets`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .targets import DEFAULT_TOKEN_ENV, AuthMode

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_TOKEN_HELP = {
    "bot": "See docs/bot-invite.md for how to create a bot and get its token.",
    "user": "See docs/faq.md for how to extract your user token from Discord web.",
}


def load_env(env_file: str | None = ".env") -> None:
    """Load ``.env`` into the process environment if it exists."""
    if env_file and Path(env_file).exists():
        load_dotenv(env_file)


def user_agent_from_env(default: str = DEFAULT_USER_AGENT) -> str:
    """UA string sent with every request; only consequential in user-token mode."""
    return os.environ.get("SCRAPER_USER_AGENT", default)


def resolve_token(auth_mode: AuthMode, token_env: str | None = None) -> str:
    """Read the token for ``auth_mode`` from ``token_env`` (or the default var).

    ``token_env`` lets one target authenticate as a different account than the
    rest of the config, e.g. ``token_env = "DISCORD_USER_TOKEN_ALT"``.
    """
    if auth_mode not in DEFAULT_TOKEN_ENV:
        raise ValueError(f"Unknown auth_mode: {auth_mode!r}")
    var = token_env or DEFAULT_TOKEN_ENV[auth_mode]
    token = os.environ.get(var, "").strip()
    if not token:
        raise RuntimeError(f"{var} is not set. {_TOKEN_HELP[auth_mode]}")
    return token


@dataclass(frozen=True)
class Settings:
    """Process-wide defaults; per-target values in ``scraper.toml`` override these."""

    auth_mode: AuthMode
    token: str
    guild_id: str | None
    output_dir: Path
    rate_limit_rps: float
    user_agent: str

    @classmethod
    def load(
        cls,
        auth_mode: AuthMode,
        *,
        env_file: str | None = ".env",
        token_env: str | None = None,
    ) -> Settings:
        load_env(env_file)
        return cls(
            auth_mode=auth_mode,
            token=resolve_token(auth_mode, token_env),
            guild_id=os.environ.get("DISCORD_GUILD_ID", "").strip() or None,
            output_dir=Path(os.environ.get("SCRAPER_OUTPUT_DIR", "./data")).expanduser().resolve(),
            rate_limit_rps=float(os.environ.get("SCRAPER_RATE_LIMIT", "5")),
            # Match a recent Chrome on macOS — keep aligned with what real Discord web sends.
            user_agent=user_agent_from_env(),
        )
