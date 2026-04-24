"""Normalized data models (pydantic v2).

The models mirror the fields we emit to JSONL. Each record also carries the
full original payload under ``raw`` so schema drift (new Discord fields) never
causes data loss.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Author(BaseModel):
    id: str
    username: str | None = None
    global_name: str | None = None
    is_bot: bool = False


class Attachment(BaseModel):
    id: str
    url: str
    filename: str | None = None
    content_type: str | None = None
    size: int | None = None


class Reaction(BaseModel):
    emoji: str
    count: int


class Message(BaseModel):
    id: str
    channel_id: str
    channel_name: str | None = None
    guild_id: str | None = None
    thread_parent_id: str | None = None
    author: Author
    content: str
    created_at: datetime
    edited_at: datetime | None = None
    reply_to_id: str | None = None
    type: int = 0
    attachments: list[Attachment] = Field(default_factory=list)
    reactions: list[Reaction] = Field(default_factory=list)
    embeds_raw: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any]
    fetched_at: datetime


class Channel(BaseModel):
    id: str
    guild_id: str | None = None
    name: str | None = None
    type: int
    parent_id: str | None = None
    topic: str | None = None
    is_thread: bool = False
    thread_parent_id: str | None = None
