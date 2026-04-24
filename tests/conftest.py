"""Shared fixtures — synthetic Discord payloads, never real data."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


@pytest.fixture
def raw_message() -> dict:
    return {
        "id": "1234567890123456789",
        "channel_id": "1111111111111111111",
        "author": {
            "id": "42",
            "username": "alice",
            "global_name": "Alice",
            "bot": False,
        },
        "content": "hello <@99> check out <#222> :custom:",
        "timestamp": "2025-04-01T12:00:00.000000+00:00",
        "edited_timestamp": None,
        "type": 0,
        "attachments": [
            {
                "id": "a1",
                "url": "https://cdn.discordapp.com/a/a1.png",
                "filename": "a1.png",
                "content_type": "image/png",
                "size": 1234,
            }
        ],
        "reactions": [
            {"emoji": {"id": None, "name": "👍"}, "count": 3},
        ],
        "embeds": [],
        "message_reference": {"message_id": "999"},
    }


@pytest.fixture
def raw_channel() -> dict:
    return {
        "id": "1111111111111111111",
        "guild_id": "guild-1",
        "name": "strategy",
        "type": 0,
        "parent_id": None,
        "topic": "strategies",
    }


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 21, 0, 0, tzinfo=UTC)
