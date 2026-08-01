"""End-to-end paginator test against a mocked httpx transport.

Never hits the real Discord API.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from discord_channel_scraper.auth import BotAuth
from discord_channel_scraper.client import DiscordClient
from discord_channel_scraper.paginate import iter_channel_messages


def _make_message(id_: int) -> dict[str, Any]:
    return {
        "id": str(id_),
        "channel_id": "c1",
        "author": {"id": "u1", "username": "bob"},
        "content": f"msg {id_}",
        "timestamp": "2025-01-01T00:00:00+00:00",
        "type": 0,
        "attachments": [],
        "embeds": [],
    }


class _FakeTransport(httpx.AsyncBaseTransport):
    """Serves pages of synthetic messages; IDs decrease each page."""

    def __init__(self, total: int, page_size: int = 100) -> None:
        self.total = total
        self.page_size = page_size
        self.calls: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        params = dict(request.url.params)
        before = params.get("before")
        # Messages numbered `total` down to 1.
        upper = int(before) - 1 if before else self.total
        page = []
        i = upper
        while i >= 1 and len(page) < self.page_size:
            page.append(_make_message(i))
            i -= 1
        return httpx.Response(200, json=page)


@pytest.mark.asyncio
async def test_paginator_walks_all_pages():
    transport = _FakeTransport(total=250, page_size=100)
    client = DiscordClient(BotAuth("t"), rate_limit_rps=1000, jitter=(0.0, 0.0))
    client._http = httpx.AsyncClient(
        base_url="https://discord.com/api/v10",
        headers={"Authorization": "Bot t"},
        transport=transport,
    )

    total = 0
    async for page in iter_channel_messages(client, "c1", page_size=100):
        total += len(page)
    await client.aclose()

    assert total == 250
    # Expect 3 requests: 250, 150, 50 messages returned.
    assert len(transport.calls) == 3


@pytest.mark.asyncio
async def test_paginator_stops_early_on_short_page():
    transport = _FakeTransport(total=30, page_size=100)
    client = DiscordClient(BotAuth("t"), rate_limit_rps=1000, jitter=(0.0, 0.0))
    client._http = httpx.AsyncClient(
        base_url="https://discord.com/api/v10",
        headers={"Authorization": "Bot t"},
        transport=transport,
    )

    total = 0
    async for page in iter_channel_messages(client, "c1", page_size=100):
        total += len(page)
    await client.aclose()

    assert total == 30
    assert len(transport.calls) == 1
