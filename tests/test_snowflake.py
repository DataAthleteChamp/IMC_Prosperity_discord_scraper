from datetime import UTC, datetime

from discord_channel_scraper.snowflake import datetime_to_snowflake, snowflake_to_datetime


def test_snowflake_roundtrip():
    dt = datetime(2024, 6, 15, 12, 30, 0, tzinfo=UTC)
    sf = datetime_to_snowflake(dt)
    back = snowflake_to_datetime(sf)
    assert abs((back - dt).total_seconds()) < 1.0


def test_snowflake_monotonic():
    a = int(datetime_to_snowflake(datetime(2024, 1, 1, tzinfo=UTC)))
    b = int(datetime_to_snowflake(datetime(2025, 1, 1, tzinfo=UTC)))
    assert b > a


def test_pre_epoch_floored():
    # Anything before Discord epoch (2015-01-01) clamps to 0.
    assert datetime_to_snowflake(datetime(2010, 1, 1, tzinfo=UTC)) == "0"


def test_naive_datetime_treated_as_utc():
    naive = datetime(2024, 1, 1, 0, 0, 0)
    aware = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert datetime_to_snowflake(naive) == datetime_to_snowflake(aware)
