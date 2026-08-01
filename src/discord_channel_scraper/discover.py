"""Enumerate every readable channel in a guild, including threads & forum posts.

Discord channel types we care about (from the docs):

- 0  ``GUILD_TEXT``       — normal text channels
- 2  ``GUILD_VOICE``      — skip (no messages for scraping purposes)
- 5  ``GUILD_ANNOUNCEMENT``
- 10 ``ANNOUNCEMENT_THREAD``
- 11 ``PUBLIC_THREAD``
- 12 ``PRIVATE_THREAD``
- 15 ``GUILD_FORUM``      — forum; each post is itself a thread of type 11
- 16 ``GUILD_MEDIA``      — media channel (forum-like)
"""

from __future__ import annotations

import logging
from typing import Any

from .client import DiscordAPIError, DiscordClient
from .models import Channel
from .normalize import normalize_channel

log = logging.getLogger(__name__)

TEXTLIKE = {0, 5}
FORUMLIKE = {15, 16}
THREADLIKE = {10, 11, 12}
SCRAPEABLE = TEXTLIKE | FORUMLIKE | THREADLIKE


async def discover_channels(client: DiscordClient, guild_id: str) -> list[Channel]:
    """Return every scrapeable channel (text, announcement, forum, thread).

    Active threads are included via ``/guilds/{guild}/threads/active``.
    Archived public+private threads are walked per text/forum parent.
    """
    channels: dict[str, Channel] = {}

    # Parent channels
    parents_raw = await client.list_guild_channels(guild_id)
    parents: list[Channel] = []
    for raw in parents_raw:
        ch = normalize_channel({**raw, "guild_id": guild_id})
        if ch.type in SCRAPEABLE:
            parents.append(ch)
            channels[ch.id] = ch

    # Active threads (cheap: one call for the whole guild)
    try:
        active = await client.list_guild_active_threads(guild_id)
        for raw in active.get("threads", []) or []:
            ch = normalize_channel({**raw, "guild_id": guild_id})
            channels[ch.id] = ch
    except DiscordAPIError as e:
        log.warning("active threads unavailable: %s", e)

    # Archived threads (per text / forum parent)
    for parent in parents:
        if parent.type not in (TEXTLIKE | FORUMLIKE):
            continue
        await _walk_archived(client, parent, guild_id, channels)

    return list(channels.values())


async def _walk_archived(
    client: DiscordClient,
    parent: Channel,
    guild_id: str,
    sink: dict[str, Any],
) -> None:
    """Fetch archived public + private threads under ``parent`` into ``sink``."""
    for fetcher in (
        client.list_archived_public_threads,
        client.list_archived_private_threads,
    ):
        before: str | None = None
        while True:
            try:
                resp = await fetcher(parent.id, before=before)
            except DiscordAPIError as e:
                if e.status in (403, 404):
                    log.debug("skip archived for %s: %s", parent.id, e)
                    break
                raise
            threads = resp.get("threads", []) or []
            for raw in threads:
                ch = normalize_channel({**raw, "guild_id": guild_id})
                sink[ch.id] = ch
            if not resp.get("has_more") or not threads:
                break
            # Paginate archived threads by the oldest archive_timestamp seen.
            meta = threads[-1].get("thread_metadata", {}) or {}
            before = meta.get("archive_timestamp")
            if not before:
                break
