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
    start_before:
        Explicit snowflake upper bound (e.g. resume from a saved cursor).
        Overrides ``until``.
    """
    before: str | None = start_before
    if before is None and until is not None:
        before = datetime_to_snowflake(until)

    since_sf = datetime_to_snowflake(since) if since else None

    while True:
        page = await client.get_messages(channel_id, before=before, limit=page_size)
        if not page:
            return

        # Pages come newest-first. Optionally trim by lower bound.
        if since_sf is not None:
            trimmed = [m for m in page if int(m["id"]) >= int(since_sf)]
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
