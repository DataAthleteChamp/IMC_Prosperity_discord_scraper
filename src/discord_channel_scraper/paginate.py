"""Snowflake-cursor pagination over ``GET /channels/{id}/messages``.

Iterates backwards from the newest message. Persists the oldest snowflake
seen so a crashed run can resume without re-downloading.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from .client import DiscordClient
from .snowflake import datetime_to_snowflake

log = logging.getLogger(__name__)


async def iter_channel_messages(
    client: DiscordClient,
    channel_id: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    after: str | None = None,
    start_before: str | None = None,
    page_size: int = 100,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Yield pages of raw message dicts, newest-to-oldest.

    Parameters
    ----------
    since:
        Lower bound (inclusive). Stop yielding once messages drop below it.
    until:
        Upper bound (inclusive). Start paginating at this snowflake.
    after:
        Exclusive lower-bound snowflake, e.g. the ``newest_seen`` watermark of a
        finished backfill. Combined with ``since`` by taking the tighter bound.
    start_before:
        Explicit snowflake upper bound (e.g. resume from a saved cursor).
        Overrides ``until``.
    """
    before: str | None = start_before
    if before is None and until is not None:
        before = datetime_to_snowflake(until)

    # Both bounds are normalised to a single inclusive floor on the message id.
    bounds = [int(datetime_to_snowflake(since)) for since in ([since] if since else [])]
    if after is not None:
        bounds.append(int(after) + 1)
    floor: int | None = max(bounds) if bounds else None

    while True:
        page = await client.get_messages(channel_id, before=before, limit=page_size)
        if not page:
            return

        # Pages come newest-first. Optionally trim by lower bound.
        if floor is not None:
            trimmed = [m for m in page if int(m["id"]) >= floor]
            if trimmed:
                yield trimmed
            if len(trimmed) < len(page):
                return
        else:
            yield page

        oldest = page[-1]["id"]
        before = str(oldest)
        log.debug("channel %s: fetched %d msgs, oldest=%s", channel_id, len(page), oldest)
        if len(page) < page_size:
            return
