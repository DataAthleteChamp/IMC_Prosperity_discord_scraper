"""Raw Discord REST payload → :class:`Message` / :class:`Channel`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .models import Attachment, Author, Channel, Message, Reaction


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    # Discord timestamps are already ISO-8601 with offset.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_author(raw: dict[str, Any]) -> Author:
    return Author(
        id=str(raw.get("id", "")),
        username=raw.get("username"),
        global_name=raw.get("global_name"),
        is_bot=bool(raw.get("bot", False)),
    )


def normalize_attachments(raw: list[dict[str, Any]]) -> list[Attachment]:
    return [
        Attachment(
            id=str(a.get("id", "")),
            url=a.get("url", ""),
            filename=a.get("filename"),
            content_type=a.get("content_type"),
            size=a.get("size"),
        )
        for a in raw
    ]


def normalize_reactions(raw: list[dict[str, Any]] | None) -> list[Reaction]:
    if not raw:
        return []
    out: list[Reaction] = []
    for r in raw:
        emoji = r.get("emoji", {}) or {}
        name = emoji.get("name") or ""
        if emoji.get("id"):
            name = f"<:{name}:{emoji['id']}>"
        out.append(Reaction(emoji=name, count=int(r.get("count", 0))))
    return out


def normalize_message(
    raw: dict[str, Any],
    *,
    channel_id: str,
    channel_name: str | None = None,
    guild_id: str | None = None,
    thread_parent_id: str | None = None,
    fetched_at: datetime | None = None,
) -> Message:
    created = _parse_iso(raw.get("timestamp")) or datetime.now(UTC)
    ref = raw.get("message_reference") or {}
    return Message(
        id=str(raw["id"]),
        channel_id=channel_id,
        channel_name=channel_name,
        guild_id=guild_id,
        thread_parent_id=thread_parent_id,
        author=normalize_author(raw.get("author", {}) or {}),
        content=raw.get("content", "") or "",
        created_at=created,
        edited_at=_parse_iso(raw.get("edited_timestamp")),
        reply_to_id=str(ref["message_id"]) if ref.get("message_id") else None,
        type=int(raw.get("type", 0)),
        attachments=normalize_attachments(raw.get("attachments", []) or []),
        reactions=normalize_reactions(raw.get("reactions")),
        embeds_raw=list(raw.get("embeds", []) or []),
        raw=raw,
        fetched_at=fetched_at or datetime.now(UTC),
    )


def normalize_channel(raw: dict[str, Any]) -> Channel:
    type_ = int(raw.get("type", 0))
    # Thread types per Discord docs: 10 (news), 11 (public), 12 (private).
    is_thread = type_ in (10, 11, 12)
    return Channel(
        id=str(raw["id"]),
        guild_id=str(raw["guild_id"]) if raw.get("guild_id") else None,
        name=raw.get("name"),
        type=type_,
        parent_id=str(raw["parent_id"]) if raw.get("parent_id") else None,
        topic=raw.get("topic"),
        is_thread=is_thread,
        thread_parent_id=str(raw["parent_id"]) if is_thread and raw.get("parent_id") else None,
    )
