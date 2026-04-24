"""AI-preprocessing stub.

Reads a scraped JSONL file, resolves ``<@id>`` mentions to usernames (using
the channel index), strips Discord markdown lightly, and writes a derived
JSONL with a ``content_clean`` field appended per record.

This is deliberately minimal — intended as a starting point for a downstream
LLM pipeline, not a finished NLP module.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import orjson

MENTION_USER_RE = re.compile(r"<@!?(\d+)>")
MENTION_CHANNEL_RE = re.compile(r"<#(\d+)>")
MENTION_ROLE_RE = re.compile(r"<@&(\d+)>")
CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):\d+>")
MD_BOLD_ITALIC_RE = re.compile(r"(\*\*|__|\*|_|~~|`)")


def load_channel_index(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {c["id"]: c.get("name", "") or "" for c in data.get("channels", [])}


def clean_content(
    raw: str,
    *,
    user_map: dict[str, str] | None = None,
    channel_map: dict[str, str] | None = None,
) -> str:
    """Produce an LLM-friendlier version of a Discord message body."""
    user_map = user_map or {}
    channel_map = channel_map or {}

    def _user(m: re.Match) -> str:
        uid = m.group(1)
        return f"@{user_map.get(uid, uid)}"

    def _channel(m: re.Match) -> str:
        cid = m.group(1)
        return f"#{channel_map.get(cid, cid)}"

    out = MENTION_USER_RE.sub(_user, raw)
    out = MENTION_CHANNEL_RE.sub(_channel, out)
    out = MENTION_ROLE_RE.sub(lambda m: f"@role:{m.group(1)}", out)
    out = CUSTOM_EMOJI_RE.sub(lambda m: f":{m.group(1)}:", out)
    out = MD_BOLD_ITALIC_RE.sub("", out)
    return out.strip()


def preprocess_file(input_path: Path, output_path: Path, channels_index: Path) -> int:
    """Augment each record with ``content_clean``. Returns rows written."""
    channel_map = load_channel_index(channels_index)
    user_map: dict[str, str] = {}
    n = 0
    with input_path.open("rb") as fin, output_path.open("wb") as fout:
        for line in fin:
            if not line.strip():
                continue
            rec: dict[str, Any] = orjson.loads(line)
            author = rec.get("author") or {}
            if author.get("id"):
                user_map[author["id"]] = author.get("username") or author.get("global_name") or ""
            rec["content_clean"] = clean_content(
                rec.get("content", ""), user_map=user_map, channel_map=channel_map
            )
            fout.write(orjson.dumps(rec, option=orjson.OPT_APPEND_NEWLINE))
            n += 1
    return n
