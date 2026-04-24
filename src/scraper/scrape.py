"""Top-level backfill orchestrator.

Flow::

    1. discover all scrapeable channels in the guild
    2. write channel index to _channels.json
    3. for each channel:
         - pick the cursor: resume from oldest_seen if backfill incomplete,
           otherwise walk forward from newest_seen
         - paginate newest-to-oldest
         - normalize, append JSONL, bump cursor every page
       bubble up to 403/404 as a warning (skip channel), other errors propagate
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from .client import DiscordAPIError, DiscordClient
from .discover import discover_channels
from .models import Channel
from .normalize import normalize_message
from .paginate import iter_channel_messages
from .writer import CursorStore, JsonlWriter, write_channel_index

log = logging.getLogger(__name__)


async def run_backfill(
    client: DiscordClient,
    guild_id: str,
    output_dir: Path,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    channels_allow: Iterable[str] | None = None,
    channels_deny: Iterable[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Run a backfill pass against ``guild_id``. Returns a summary dict."""
    writer = JsonlWriter(output_dir)
    cursors = CursorStore(output_dir)

    log.info("discovering channels for guild %s ...", guild_id)
    channels = await discover_channels(client, guild_id)
    log.info("discovered %d scrapeable channels/threads", len(channels))
    write_channel_index(output_dir, channels)

    allow = set(channels_allow) if channels_allow else None
    deny = set(channels_deny) if channels_deny else set()

    selected = [c for c in channels if (allow is None or c.id in allow) and c.id not in deny]
    log.info("%d channels selected after filters", len(selected))

    if dry_run:
        return {
            "discovered": len(channels),
            "selected": len(selected),
            "channels": [c.model_dump(mode="json") for c in selected],
            "dry_run": True,
        }

    total_messages = 0
    skipped: list[str] = []

    for ch in selected:
        try:
            n = await _backfill_channel(
                client,
                ch,
                writer=writer,
                cursors=cursors,
                guild_id=guild_id,
                since=since,
                until=until,
            )
            total_messages += n
        except DiscordAPIError as e:
            if e.status in (403, 404):
                log.warning("skip %s (%s): %s", ch.id, ch.name, e)
                skipped.append(ch.id)
                continue
            raise
        cursors.flush()

    cursors.flush()
    return {
        "discovered": len(channels),
        "selected": len(selected),
        "scraped_messages": total_messages,
        "skipped": skipped,
    }


async def _backfill_channel(
    client: DiscordClient,
    ch: Channel,
    *,
    writer: JsonlWriter,
    cursors: CursorStore,
    guild_id: str,
    since: datetime | None,
    until: datetime | None,
) -> int:
    entry = cursors.get(ch.id)
    # Resume policy: if we haven't finished backfilling, continue walking
    # *older* messages from the oldest_seen watermark.
    start_before: str | None = None
    if entry and not entry.get("backfill_done"):
        start_before = entry.get("oldest_seen")
        if start_before:
            log.info("resume %s from oldest_seen=%s", ch.id, start_before)

    total = 0
    any_yielded = False
    try:
        async for page in iter_channel_messages(
            client,
            ch.id,
            since=since,
            until=until,
            start_before=start_before,
        ):
            any_yielded = True
            msgs = [
                normalize_message(
                    m,
                    channel_id=ch.id,
                    channel_name=ch.name,
                    guild_id=guild_id,
                    thread_parent_id=ch.thread_parent_id,
                )
                for m in page
            ]
            n = writer.append(ch.id, msgs)
            total += n
            newest = page[0]["id"]
            oldest = page[-1]["id"]
            cursors.update(ch.id, oldest_seen=oldest, newest_seen=newest)
            await asyncio.sleep(0)  # cooperative
            log.info("%s (%s): +%d msgs (oldest=%s)", ch.id, ch.name, n, oldest)
    except DiscordAPIError:
        cursors.flush()
        raise

    cursors.update(ch.id, backfill_done=True)
    if not any_yielded:
        log.info("%s (%s): no new messages", ch.id, ch.name)
    return total
