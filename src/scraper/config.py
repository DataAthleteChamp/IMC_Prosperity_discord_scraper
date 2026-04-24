"""Runtime configuration loaded from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

AuthMode = Literal["bot", "user"]


@dataclass(frozen=True)
class Settings:
    auth_mode: AuthMode
    token: str
    guild_id: str | None
    output_dir: Path
    rate_limit_rps: float
    user_agent: str

    @classmethod
    def load(cls, auth_mode: AuthMode, *, env_file: str | None = ".env") -> Settings:
        if env_file and Path(env_file).exists():
            load_dotenv(env_file)

        if auth_mode == "bot":
            token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
            if not token:
                raise RuntimeError(
                    "DISCORD_BOT_TOKEN is not set. "
                    "See docs/bot-invite.md for how to create a bot and get the token."
                )
        elif auth_mode == "user":
            token = os.environ.get("DISCORD_USER_TOKEN", "").strip()
            if not token:
                raise RuntimeError(
                    "DISCORD_USER_TOKEN is not set. "
                    "See README for how to extract your user token from Discord web."
                )
        else:
            raise ValueError(f"Unknown auth_mode: {auth_mode!r}")

        return cls(
            auth_mode=auth_mode,
            token=token,
            guild_id=os.environ.get("DISCORD_GUILD_ID", "").strip() or None,
            output_dir=Path(os.environ.get("SCRAPER_OUTPUT_DIR", "./data")).resolve(),
            rate_limit_rps=float(os.environ.get("SCRAPER_RATE_LIMIT", "5")),
            # Match a recent Chrome on macOS — keep aligned with what real Discord web sends.
            user_agent=os.environ.get(
                "SCRAPER_USER_AGENT",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36",
            ),
        )
