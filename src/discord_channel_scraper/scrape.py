"""Top-level backfill orchestrator.

Flow::

    1. discover all scrapeable channels in the guild
    2. write channel index to _channels.json
    3. apply the target's allow/deny channel selectors
    4. for each channel:
         - pick the cursor: resume from oldest_seen if backfill incomplete,
           otherwise walk forward from newest_seen
         - paginate newest-to-oldest
         - normalize, append JSONL, bump cursor every page
       bubble up to 403/404 as a warning (skip channel), other errors propagate

:func:`run_targets` drives several servers in one command, sequentially, so
that a single account never issues parallel bursts to Discord.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

from .auth import from_mode
from .client import DiscordAPIError, DiscordClient
from .config import DEFAULT_USER_AGENT, resolve_token
from .discover import discover_channels
from .models import Channel
from .normalize import normalize_message
from .paginate import iter_channel_messages
from .selectors import select_channels
from .targets import Target
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

    selection = select_channels(channels, allow=channels_allow, deny=channels_deny)
    selected = selection.selected
    for bad in selection.unmatched_allow:
        log.warning("channel selector %r matched nothing in guild %s", bad, guild_id)
    for bad in selection.unmatched_deny:
        log.warning("exclude selector %r matched nothing in guild %s", bad, guild_id)
    log.info("%d channels selected after filters", len(selected))

    if dry_run:
        return {
            "guild_id": guild_id,
            "output_dir": str(output_dir),
            "discovered": len(channels),
            "selected": len(selected),
            "channels": [c.model_dump(mode="json") for c in selected],
            "unmatched_selectors": selection.unmatched_allow + selection.unmatched_deny,
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
        "guild_id": guild_id,
        "output_dir": str(output_dir),
        "discovered": len(channels),
        "selected": len(selected),
        "scraped_messages": total_messages,
        "skipped": skipped,
        "unmatched_selectors": selection.unmatched_allow + selection.unmatched_deny,
    }


async def run_target(
    target: Target,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    rate_limit: float | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    dry_run: bool = False,
) -> dict:
    """Backfill one configured :class:`~.targets.Target` with its own client."""
    token = resolve_token(target.auth_mode, target.token_env)
    target.output_dir.mkdir(parents=True, exist_ok=True)
    rps = rate_limit or target.rate_limit or 5.0
    log.info(
        "target %r -> guild %s, out=%s, auth=%s, %.1f req/s",
        target.name,
        target.guild_id,
        target.output_dir,
        target.auth_mode,
        rps,
    )
    async with DiscordClient(
        from_mode(target.auth_mode, token),
        rate_limit_rps=rps,
        user_agent=user_agent,
    ) as client:
        return await run_backfill(
            client,
            target.guild_id,
            target.output_dir,
            since=since if since is not None else target.since,
            until=until if until is not None else target.until,
            channels_allow=target.channels,
            channels_deny=target.exclude_channels,
            dry_run=dry_run,
        )


async def run_targets(
    targets: Sequence[Target],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    rate_limit: float | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    dry_run: bool = False,
    continue_on_error: bool = True,
) -> dict:
    """Backfill several targets one after another. Returns a per-target summary."""
    results: dict[str, dict] = {}
    for target in targets:
        try:
            results[target.name] = await run_target(
                target,
                since=since,
                until=until,
                rate_limit=rate_limit,
                user_agent=user_agent,
                dry_run=dry_run,
            )
        except Exception as e:  # one bad target must not lose the rest
            log.error("target %r failed: %s", target.name, e)
            results[target.name] = {"error": f"{type(e).__name__}: {e}"}
            if not continue_on_error:
                raise
    return results


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
    # *older* messages from the oldest_seen watermark. Once a channel is fully
    # backfilled, later runs only pick up what arrived after newest_seen —
    # without that bound every re-run would append the whole channel again.
    start_before: str | None = None
    start_after: str | None = None
    if entry and not entry.get("backfill_done"):
        start_before = entry.get("oldest_seen")
        if start_before:
            log.info("resume %s from oldest_seen=%s", ch.id, start_before)
    elif entry and since is None:
        start_after = entry.get("newest_seen")
        if start_after:
            log.info("incremental %s from newest_seen=%s", ch.id, start_after)

    total = 0
    any_yielded = False
    try:
        async for page in iter_channel_messages(
            client,
            ch.id,
            since=since,
            until=until,
            after=start_after,
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
