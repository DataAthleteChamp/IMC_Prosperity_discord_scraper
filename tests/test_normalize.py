from scraper.normalize import normalize_channel, normalize_message


def test_normalize_message_basic(raw_message):
    m = normalize_message(
        raw_message,
        channel_id="1111111111111111111",
        channel_name="strategy",
        guild_id="guild-1",
    )
    assert m.id == raw_message["id"]
    assert m.author.username == "alice"
    assert m.author.is_bot is False
    assert m.content.startswith("hello <@99>")
    assert m.channel_name == "strategy"
    assert m.guild_id == "guild-1"
    assert m.reply_to_id == "999"
    assert len(m.attachments) == 1
    assert m.attachments[0].url.startswith("https://")
    assert m.reactions[0].emoji == "👍"
    assert m.reactions[0].count == 3
    # raw payload is preserved exactly
    assert m.raw["id"] == raw_message["id"]


def test_normalize_message_missing_optionals():
    minimal = {
        "id": "1",
        "author": {"id": "2"},
        "content": "",
        "timestamp": "2025-01-01T00:00:00+00:00",
    }
    m = normalize_message(minimal, channel_id="c1")
    assert m.edited_at is None
    assert m.reply_to_id is None
    assert m.attachments == []
    assert m.reactions == []


def test_normalize_channel_detects_thread():
    raw = {"id": "t1", "guild_id": "g1", "name": "my-thread", "type": 11, "parent_id": "c1"}
    ch = normalize_channel(raw)
    assert ch.is_thread is True
    assert ch.thread_parent_id == "c1"


def test_normalize_channel_text(raw_channel):
    ch = normalize_channel(raw_channel)
    assert ch.is_thread is False
    assert ch.thread_parent_id is None
    assert ch.name == "strategy"
