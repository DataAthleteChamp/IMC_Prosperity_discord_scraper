"""Minimal example: run a dry-run discovery against a guild.

Usage:

    cp ../.env.example ../.env   # fill in DISCORD_USER_TOKEN, DISCORD_GUILD_ID
    python examples/dry_run.py
"""

from __future__ import annotations

import asyncio
import json

from scraper.auth import from_mode
from scraper.client import DiscordClient
from scraper.config import Settings
from scraper.discover import discover_channels


async def main() -> None:
    settings = Settings.load("user")
    assert settings.guild_id, "Set DISCORD_GUILD_ID in .env"
    async with DiscordClient(
        from_mode("user", settings.token),
        rate_limit_rps=settings.rate_limit_rps,
        user_agent=settings.user_agent,
    ) as client:
        channels = await discover_channels(client, settings.guild_id)
    print(json.dumps([c.model_dump(mode="json") for c in channels], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
