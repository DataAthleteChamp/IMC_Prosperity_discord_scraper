from scraper.auth import BotAuth, UserAuth, from_mode


def test_bot_auth_prefixes_token():
    assert BotAuth("abc").header() == "Bot abc"


def test_user_auth_is_raw():
    assert UserAuth("abc").header() == "abc"


def test_from_mode_dispatch():
    assert isinstance(from_mode("bot", "t"), BotAuth)
    assert isinstance(from_mode("user", "t"), UserAuth)


def test_from_mode_rejects_unknown():
    try:
        from_mode("nope", "t")
    except ValueError:
        return
    raise AssertionError("should have raised")
