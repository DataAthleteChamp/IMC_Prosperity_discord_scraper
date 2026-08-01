"""On-disk output: JSONL messages + channel index + cursors.

Directory layout produced in ``output_dir``::

    data/
    ├─ _channels.json        # all discovered channels, keyed by id
    ├─ _cursors.json         # per-channel watermarks for resumable runs
    └─ <channel_id>.jsonl    # one file per channel, newest-to-oldest append
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from .models import Channel, Message

log = logging.getLogger(__name__)

CURSORS_FILE = "_cursors.json"
CHANNELS_FILE = "_channels.json"


class JsonlWriter:
    """Append-only JSONL writer, one file per channel."""

    def __init__(self, output_dir: Path) -> None:
        self._dir = output_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def path(self, channel_id: str) -> Path:
        return self._dir / f"{channel_id}.jsonl"

    def append(self, channel_id: str, messages: Iterable[Message]) -> int:
        path = self.path(channel_id)
        count = 0
        with path.open("ab") as f:
            for msg in messages:
                f.write(
                    orjson.dumps(
                        msg.model_dump(mode="json"),
                        option=orjson.OPT_APPEND_NEWLINE | orjson.OPT_UTC_Z,
                    )
                )
                count += 1
        return count


class CursorStore:
    """Per-channel snowflake watermarks; JSON-backed.

    Schema:

    .. code-block:: json

        {
          "channels": {
            "<channel_id>": {
              "oldest_seen":   "1234567890",
              "newest_seen":   "9876543210",
              "backfill_done": false,
              "updated_at":    "2026-04-24T21:40:00Z"
            }
          }
        }
    """

    def __init__(self, output_dir: Path) -> None:
        self._path = output_dir / CURSORS_FILE
        self._data: dict[str, Any] = {"channels": {}}
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text())
            except json.JSONDecodeError:
                log.warning("cursors file is corrupt, starting fresh: %s", self._path)
                self._data = {"channels": {}}

    def get(self, channel_id: str) -> dict[str, Any]:
        entry: dict[str, Any] = self._data["channels"].get(channel_id, {})
        return entry

    def update(
        self,
        channel_id: str,
        *,
        oldest_seen: str | None = None,
        newest_seen: str | None = None,
        backfill_done: bool | None = None,
    ) -> None:
        entry: dict[str, Any] = self._data["channels"].setdefault(channel_id, {})
        if oldest_seen is not None:
            prev = entry.get("oldest_seen")
            if prev is None or int(oldest_seen) < int(prev):
                entry["oldest_seen"] = oldest_seen
        if newest_seen is not None:
            prev = entry.get("newest_seen")
            if prev is None or int(newest_seen) > int(prev):
                entry["newest_seen"] = newest_seen
        if backfill_done is not None:
            entry["backfill_done"] = backfill_done
        entry["updated_at"] = datetime.now(UTC).isoformat()

    def flush(self) -> None:
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True))
        tmp.replace(self._path)


def write_channel_index(output_dir: Path, channels: list[Channel]) -> None:
    path = output_dir / CHANNELS_FILE
    payload = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "channels": [c.model_dump(mode="json") for c in channels],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
