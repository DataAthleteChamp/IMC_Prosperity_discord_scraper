"""Channel filtering: turn user-supplied selectors into a concrete channel set.

A *selector* is either a channel ID (``"333333333333333333"``) or a channel
name (``"round-5"``, ``"#round-5"``, case-insensitive). Names are far easier to
put in a config file than snowflakes, so both are accepted everywhere
``channels`` / ``exclude_channels`` are.

Selecting a parent also selects everything under it: threads and forum posts
inherit their parent's decision unless they match a selector themselves. That
makes ``channels = ["round-5"]`` do the obvious thing for a forum channel.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .models import Channel


@dataclass(frozen=True)
class Selection:
    """Outcome of applying allow/deny selectors to a discovered channel list."""

    selected: list[Channel] = field(default_factory=list)
    unmatched_allow: list[str] = field(default_factory=list)
    unmatched_deny: list[str] = field(default_factory=list)


def _normalize(selectors: Iterable[str] | None) -> tuple[set[str], set[str]]:
    """Split selectors into (ids, lowercased names)."""
    ids: set[str] = set()
    names: set[str] = set()
    for raw in selectors or ():
        value = str(raw).strip().lstrip("#")
        if not value:
            continue
        if value.isdigit():
            ids.add(value)
        else:
            names.add(value.casefold())
    return ids, names


def _matcher(
    channels: Iterable[Channel], ids: set[str], names: set[str]
) -> tuple[Callable[[Channel], bool], set[str]]:
    """Build a predicate that also honours parent-channel matches."""
    by_id = {c.id: c for c in channels}

    # Expand name selectors to the IDs of the channels bearing those names, so
    # a thread can be matched via its parent's *name* as well as its ID.
    matched_ids = set(ids)
    for ch in by_id.values():
        if ch.name and ch.name.casefold() in names:
            matched_ids.add(ch.id)

    def matches(ch: Channel) -> bool:
        if ch.id in matched_ids:
            return True
        # Walk up the parent chain (threads -> forum/text parent).
        seen: set[str] = set()
        parent_id = ch.thread_parent_id or ch.parent_id
        while parent_id and parent_id not in seen:
            if parent_id in matched_ids:
                return True
            seen.add(parent_id)
            parent = by_id.get(parent_id)
            parent_id = (parent.thread_parent_id or parent.parent_id) if parent else None
        return False

    return matches, matched_ids


def _unmatched(channels: Iterable[Channel], selectors: Iterable[str] | None) -> list[str]:
    """Selectors that matched no discovered channel — usually typos."""
    known_ids = {c.id for c in channels}
    known_names = {c.name.casefold() for c in channels if c.name}
    out: list[str] = []
    for raw in selectors or ():
        value = str(raw).strip().lstrip("#")
        if not value:
            continue
        if value.isdigit():
            if value not in known_ids:
                out.append(value)
        elif value.casefold() not in known_names:
            out.append(value)
    return out


def select_channels(
    channels: list[Channel],
    *,
    allow: Iterable[str] | None = None,
    deny: Iterable[str] | None = None,
) -> Selection:
    """Filter ``channels``. An empty/omitted ``allow`` means "everything"."""
    allow = list(allow or ())
    deny = list(deny or ())

    allow_ids, allow_names = _normalize(allow)
    deny_ids, deny_names = _normalize(deny)

    is_allowed, _ = _matcher(channels, allow_ids, allow_names)
    is_denied, _ = _matcher(channels, deny_ids, deny_names)

    has_allow = bool(allow_ids or allow_names)
    selected = [c for c in channels if (not has_allow or is_allowed(c)) and not is_denied(c)]

    return Selection(
        selected=selected,
        unmatched_allow=_unmatched(channels, allow),
        unmatched_deny=_unmatched(channels, deny),
    )
