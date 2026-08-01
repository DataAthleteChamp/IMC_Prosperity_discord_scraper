"""Channel selection by ID, by name, and via parent channels."""

from __future__ import annotations

import pytest

from discord_channel_scraper.models import Channel
from discord_channel_scraper.selectors import select_channels


@pytest.fixture
def channels() -> list[Channel]:
    return [
        Channel(id="1", name="general", type=0),
        Channel(id="2", name="round-5", type=15),  # forum
        Channel(
            id="3", name="Team ideas", type=11, parent_id="2", is_thread=True, thread_parent_id="2"
        ),
        Channel(id="4", name="off-topic", type=0),
        Channel(id="5", name="rant", type=11, parent_id="4", is_thread=True, thread_parent_id="4"),
    ]


def _names(result) -> list[str]:
    return [c.name for c in result.selected]


def test_no_selectors_returns_everything(channels: list[Channel]) -> None:
    assert len(select_channels(channels).selected) == len(channels)


def test_selects_by_id(channels: list[Channel]) -> None:
    assert _names(select_channels(channels, allow=["1"])) == ["general"]


def test_selects_by_name_case_insensitively_and_ignores_hash(channels: list[Channel]) -> None:
    assert _names(select_channels(channels, allow=["#GENERAL"])) == ["general"]


def test_selecting_a_forum_includes_its_threads(channels: list[Channel]) -> None:
    assert _names(select_channels(channels, allow=["round-5"])) == ["round-5", "Team ideas"]


def test_thread_can_be_selected_on_its_own(channels: list[Channel]) -> None:
    assert _names(select_channels(channels, allow=["Team ideas"])) == ["Team ideas"]


def test_exclusion_beats_inclusion_and_cascades_to_threads(channels: list[Channel]) -> None:
    result = select_channels(channels, deny=["off-topic"])
    assert _names(result) == ["general", "round-5", "Team ideas"]


def test_mixed_ids_and_names(channels: list[Channel]) -> None:
    result = select_channels(channels, allow=["general", "2"], deny=["Team ideas"])
    assert _names(result) == ["general", "round-5"]


def test_unmatched_selectors_are_reported(channels: list[Channel]) -> None:
    result = select_channels(channels, allow=["general", "typo-channel"], deny=["999"])
    assert result.unmatched_allow == ["typo-channel"]
    assert result.unmatched_deny == ["999"]
    assert _names(result) == ["general"]


def test_empty_selectors_are_ignored(channels: list[Channel]) -> None:
    assert len(select_channels(channels, allow=["", "  "]).selected) == len(channels)
