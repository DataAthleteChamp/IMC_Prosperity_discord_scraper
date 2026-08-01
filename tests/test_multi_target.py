"""End-to-end multi-server backfill against a mocked Discord API.

Proves the headline behaviour: one account, two guilds, two channel selections,
two independent output directories. Never touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from discord_channel_scraper.scrape import run_targets
from discord_channel_scraper.targets import Target

GUILDS: dict[str, list[dict[str, Any]]] = {
    "111": [
        {"id": "c1", "name": "general", "type": 0},
        {"id": "c2", "name": "off-topic", "type": 0},
    ],
    "222": [
        {"id": "c3", "name": "strategy", "type": 0},
        {"id": "c4", "name": "memes", "type": 0},
    ],
}

MESSAGES_PER_CHANNEL = 2


def _message(channel_id: str, n: int) -> dict[str, Any]:
    """Message ``n`` of ``channel_id``; higher n means newer (larger snowflake)."""
    return {
        "id": f"{channel_id[-1]}{n:04d}",
        "channel_id": channel_id,
        "author": {"id": "u1", "username": "bob"},
        "content": f"{channel_id} message {n}",
        "timestamp": "2025-01-01T00:00:00+00:00",
        "type": 0,
        "attachments": [],
        "embeds": [],
    }


class _FakeDiscord(httpx.AsyncBaseTransport):
    """Serves a fixed channel history, paginated newest-first via ``before``."""

    def __init__(self) -> None:
        self.message_calls: list[str] = []
        self.extra_messages = 0

    def _history(self, channel_id: str) -> list[dict[str, Any]]:
        total = MESSAGES_PER_CHANNEL + self.extra_messages
        return [_message(channel_id, n) for n in range(total, 0, -1)]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v10")
        if path.startswith("/guilds/") and path.endswith("/channels"):
            return httpx.Response(200, json=GUILDS[path.split("/")[2]])
        if path.endswith("/threads/active"):
            return httpx.Response(200, json={"threads": [], "members": [], "has_more": False})
        if "/threads/archived/" in path:
            return httpx.Response(200, json={"threads": [], "has_more": False})
        if path.endswith("/messages"):
            channel_id = path.split("/")[2]
            self.message_calls.append(channel_id)
            params = dict(request.url.params)
            history = self._history(channel_id)
            if before := params.get("before"):
                history = [m for m in history if int(m["id"]) < int(before)]
            return httpx.Response(200, json=history[: int(params.get("limit", 100))])
        return httpx.Response(404, json={"message": "unexpected path"})


@pytest.fixture
def fake_discord(monkeypatch: pytest.MonkeyPatch) -> _FakeDiscord:
    """Route every DiscordClient through the fake transport, with no pacing."""
    transport = _FakeDiscord()
    monkeypatch.setenv("DISCORD_USER_TOKEN", "fake-token")

    from discord_channel_scraper import client as client_module

    real_init = client_module.DiscordClient.__init__

    def patched_init(self: Any, auth: Any, **kwargs: Any) -> None:
        kwargs["rate_limit_rps"] = 1000
        real_init(self, auth, jitter=(0.0, 0.0), **kwargs)
        self._http = httpx.AsyncClient(
            base_url=client_module.API_BASE,
            headers={"Authorization": auth.header()},
            transport=transport,
        )

    monkeypatch.setattr(client_module.DiscordClient, "__init__", patched_init)
    return transport


@pytest.mark.asyncio
async def test_two_servers_write_to_separate_directories(
    tmp_path: Path, fake_discord: _FakeDiscord
) -> None:
    one = tmp_path / "server-one"
    two = tmp_path / "server-two"
    targets = [
        Target(name="one", guild_id="111", output_dir=one, channels=("general",)),
        Target(name="two", guild_id="222", output_dir=two, exclude_channels=("memes",)),
    ]

    summary = await run_targets(targets)

    assert summary["one"]["scraped_messages"] == MESSAGES_PER_CHANNEL
    assert summary["two"]["scraped_messages"] == MESSAGES_PER_CHANNEL

    # Each target only fetched the channels its selectors allow.
    assert sorted(set(fake_discord.message_calls)) == ["c1", "c3"]

    assert (one / "c1.jsonl").exists()
    assert not (one / "c2.jsonl").exists()
    assert (two / "c3.jsonl").exists()
    assert not (two / "c4.jsonl").exists()

    # Cursors are per-directory, so the two servers never clobber each other.
    for directory, channel_id in ((one, "c1"), (two, "c3")):
        cursors = json.loads((directory / "_cursors.json").read_text())
        assert cursors["channels"][channel_id]["backfill_done"] is True
        assert set(cursors["channels"]) == {channel_id}


@pytest.mark.asyncio
async def test_rerunning_a_finished_target_does_not_duplicate_messages(
    tmp_path: Path, fake_discord: _FakeDiscord
) -> None:
    """The documented 'just re-run it' workflow must be idempotent."""
    out = tmp_path / "one"
    targets = [Target(name="one", guild_id="111", output_dir=out, channels=("general",))]

    first = await run_targets(targets)
    second = await run_targets(targets)
    third = await run_targets(targets)

    assert first["one"]["scraped_messages"] == MESSAGES_PER_CHANNEL
    assert second["one"]["scraped_messages"] == 0
    assert third["one"]["scraped_messages"] == 0

    lines = (out / "c1.jsonl").read_text().splitlines()
    ids = [json.loads(line)["id"] for line in lines]
    assert len(ids) == len(set(ids)) == MESSAGES_PER_CHANNEL

    cursors = json.loads((out / "_cursors.json").read_text())
    assert cursors["channels"]["c1"]["newest_seen"] == max(ids)


@pytest.mark.asyncio
async def test_incremental_run_picks_up_newer_messages_only(
    tmp_path: Path, fake_discord: _FakeDiscord
) -> None:
    out = tmp_path / "one"
    targets = [Target(name="one", guild_id="111", output_dir=out, channels=("general",))]

    await run_targets(targets)
    fake_discord.extra_messages = 2  # two newer messages arrive in the channel
    summary = await run_targets(targets)

    assert summary["one"]["scraped_messages"] == 2
    ids = [json.loads(line)["id"] for line in (out / "c1.jsonl").read_text().splitlines()]
    assert len(ids) == len(set(ids)) == MESSAGES_PER_CHANNEL + 2


@pytest.mark.asyncio
async def test_one_failing_target_does_not_abort_the_others(
    tmp_path: Path, fake_discord: _FakeDiscord
) -> None:
    targets = [
        Target(name="broken", guild_id="999", output_dir=tmp_path / "broken"),
        Target(name="ok", guild_id="111", output_dir=tmp_path / "ok", channels=("general",)),
    ]

    summary = await run_targets(targets)

    assert "error" in summary["broken"]
    assert summary["ok"]["scraped_messages"] == MESSAGES_PER_CHANNEL


@pytest.mark.asyncio
async def test_dry_run_discovers_without_fetching_messages(
    tmp_path: Path, fake_discord: _FakeDiscord
) -> None:
    targets = [Target(name="one", guild_id="111", output_dir=tmp_path / "one")]

    summary = await run_targets(targets, dry_run=True)

    assert summary["one"]["dry_run"] is True
    assert summary["one"]["discovered"] == 2
    assert fake_discord.message_calls == []
    assert not list((tmp_path / "one").glob("*.jsonl"))
