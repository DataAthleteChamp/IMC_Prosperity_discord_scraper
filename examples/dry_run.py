"""Minimal example: run a dry-run discovery against every configured target.

Usage::

    cp ../.env.example ../.env          # fill in DISCORD_USER_TOKEN
    discord-channel-scraper init        # creates scraper.toml, then edit it
    python examples/dry_run.py
"""

from __future__ import annotations

import asyncio
import json

from discord_channel_scraper.config import load_env, user_agent_from_env
from discord_channel_scraper.scrape import run_targets
from discord_channel_scraper.targets import find_config, load_config


async def main() -> None:
    load_env()
    path = find_config()
    assert path is not None, "No scraper.toml found — run 'discord-channel-scraper init'"
    config = load_config(path)
    summary = await run_targets(
        config.select(None),
        user_agent=user_agent_from_env(),
        dry_run=True,
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
