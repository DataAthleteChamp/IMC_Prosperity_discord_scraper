import json

from discord_channel_scraper.models import Channel
from discord_channel_scraper.normalize import normalize_message
from discord_channel_scraper.writer import CursorStore, JsonlWriter, write_channel_index


def test_jsonl_writer_appends(tmp_path, raw_message):
    w = JsonlWriter(tmp_path)
    msg = normalize_message(raw_message, channel_id="c1")
    w.append("c1", [msg])
    w.append("c1", [msg])
    text = (tmp_path / "c1.jsonl").read_text().strip().splitlines()
    assert len(text) == 2
    first = json.loads(text[0])
    assert first["id"] == raw_message["id"]
    assert first["author"]["username"] == "alice"


def test_cursor_store_persists(tmp_path):
    store = CursorStore(tmp_path)
    store.update("c1", oldest_seen="500", newest_seen="1000")
    store.flush()

    store2 = CursorStore(tmp_path)
    assert store2.get("c1")["oldest_seen"] == "500"
    assert store2.get("c1")["newest_seen"] == "1000"


def test_cursor_update_keeps_extremes(tmp_path):
    store = CursorStore(tmp_path)
    store.update("c1", oldest_seen="500", newest_seen="1000")
    # A later update with a *larger* oldest shouldn't overwrite.
    store.update("c1", oldest_seen="900")
    # A later update with a *smaller* newest shouldn't overwrite.
    store.update("c1", newest_seen="800")
    assert store.get("c1")["oldest_seen"] == "500"
    assert store.get("c1")["newest_seen"] == "1000"


def test_cursor_backfill_done_flag(tmp_path):
    store = CursorStore(tmp_path)
    store.update("c1", backfill_done=True)
    store.flush()
    assert CursorStore(tmp_path).get("c1")["backfill_done"] is True


def test_channel_index_written(tmp_path):
    channels = [Channel(id="c1", type=0, name="general")]
    write_channel_index(tmp_path, channels)
    data = json.loads((tmp_path / "_channels.json").read_text())
    assert data["channels"][0]["id"] == "c1"
    assert data["channels"][0]["name"] == "general"
