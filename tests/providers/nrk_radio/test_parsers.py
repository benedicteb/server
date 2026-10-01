"""Tests for the NRK Radio payload parsers."""

from __future__ import annotations

from music_assistant.providers.nrk_radio.parsers import (
    parse_stream_metadata,
    select_current_element,
    select_image_url,
)

from .conftest import make_channel, make_element


def test_select_image_url() -> None:
    """The 600 px poster is preferred, then the largest; no posters means no image."""
    assert select_image_url(make_channel("p1", "NRK P1")) == "https://gfx.nrk.no/p1-600"
    channel = make_channel("p1", "NRK P1", widths=(300, 1920, 960))
    assert select_image_url(channel) == "https://gfx.nrk.no/p1-1920"
    assert select_image_url(make_channel("p1", "NRK P1", widths=())) is None


def test_select_current_element_takes_latest_present() -> None:
    """With several Present entries, the one that started last wins, regardless of order."""
    elements = [
        make_element("Older", relative="Present", start_ms=2000),
        make_element("Past song", relative="Past", start_ms=9000),
        make_element("Newer", relative="Present", start_ms=3000),
        make_element("No start", relative="Present", start_ms=None),
        None,
    ]
    current = select_current_element(elements)
    assert current is not None
    assert current["title"] == "Newer"


def test_parse_stream_metadata() -> None:
    """A song maps to title, artist and artwork; speech shows the programme as artist line."""
    song = make_element(
        "Memoarer", artist="Undergrunn", relative="Present", image="https://gfx.nrk.no/cover"
    )
    metadata = parse_stream_metadata([song])
    assert metadata is not None
    assert (metadata.title, metadata.artist) == ("Memoarer", "Undergrunn")
    assert metadata.image_url == "https://gfx.nrk.no/cover"

    speech = make_element("Åpen prat", kind="News", program="Siesta", relative="Present")
    metadata = parse_stream_metadata([speech])
    assert metadata is not None
    assert (metadata.title, metadata.artist) == ("Åpen prat", "Siesta")
    assert metadata.image_url is None

    assert parse_stream_metadata([make_element("Past song")]) is None
