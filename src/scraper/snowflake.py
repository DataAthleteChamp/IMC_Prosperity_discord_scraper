"""Discord snowflake helpers.

A snowflake is a 64-bit integer ID whose upper bits encode the creation time.
Because messages are addressed by snowflake, we can convert any datetime to a
synthetic ID and use it as a pagination bound (``before=`` / ``after=``).
"""

from __future__ import annotations

from datetime import UTC, datetime

DISCORD_EPOCH_MS = 1_420_070_400_000  # 2015-01-01T00:00:00Z


def datetime_to_snowflake(dt: datetime) -> str:
    """Convert a UTC datetime to the smallest snowflake with that timestamp."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    ms = int(dt.astimezone(UTC).timestamp() * 1000)
    return str(max(0, (ms - DISCORD_EPOCH_MS)) << 22)


def snowflake_to_datetime(snowflake: str | int) -> datetime:
    sid = int(snowflake)
    ms = (sid >> 22) + DISCORD_EPOCH_MS
    return datetime.fromtimestamp(ms / 1000, tz=UTC)
