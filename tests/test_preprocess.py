from scraper.preprocess import clean_content


def test_clean_resolves_user_mention():
    out = clean_content("hi <@42>!", user_map={"42": "alice"})
    assert "@alice" in out
    assert "<@42>" not in out


def test_clean_resolves_channel_mention():
    out = clean_content("see <#222>", channel_map={"222": "general"})
    assert "#general" in out


def test_clean_strips_custom_emoji():
    out = clean_content("nice <:party:123>")
    assert ":party:" in out
    assert "<:party:123>" not in out


def test_clean_strips_markdown():
    out = clean_content("**bold** _italic_ ~~strike~~ `code`")
    assert "**" not in out
    assert "_" not in out
    assert "~~" not in out
    assert "`" not in out


def test_clean_unknown_user_falls_back_to_id():
    out = clean_content("hi <@42>", user_map={})
    assert "@42" in out
