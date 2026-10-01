"""Tests for the NRK Radio payload parsers."""

from __future__ import annotations

from music_assistant.providers.nrk_radio.parsers import (
    is_district_channel,
    parse_radio,
    select_image_url,
)

from .conftest import DOMAIN, INSTANCE_ID, make_channel


def test_is_district_channel() -> None:
    """Only districtChannel entries count as district channels."""
    assert is_district_channel(make_channel("p1_troms", "NRK P1 Troms", "districtChannel"))
    assert not is_district_channel(make_channel("p1", "NRK P1"))


def test_select_image_url_prefers_600px() -> None:
    """The 600 px poster is chosen when it exists."""
    assert select_image_url(make_channel("p1", "NRK P1")) == "https://gfx.nrk.no/p1-600"


def test_select_image_url_falls_back_to_largest() -> None:
    """Without a 600 px poster the largest one is used."""
    channel = make_channel("p1", "NRK P1", widths=(300, 1920, 960))
    assert select_image_url(channel) == "https://gfx.nrk.no/p1-1920"


def test_select_image_url_without_posters() -> None:
    """A channel without square posters has no image."""
    assert select_image_url(make_channel("p1", "NRK P1", widths=())) is None
    channel = make_channel("p1", "NRK P1")
    channel["_embedded"]["playback"]["squarePosters"] = []
    assert select_image_url(channel) is None


def test_parse_radio() -> None:
    """A channel becomes a Radio with NRK's id, title and poster."""
    radio = parse_radio(make_channel("p1_troms", "NRK P1 Troms"), INSTANCE_ID, DOMAIN)

    assert radio.item_id == "p1_troms"
    assert radio.name == "NRK P1 Troms"
    assert radio.provider == INSTANCE_ID
    mapping = next(iter(radio.provider_mappings))
    assert mapping.item_id == "p1_troms"
    assert mapping.provider_domain == DOMAIN
    assert mapping.provider_instance == INSTANCE_ID
    assert radio.metadata.images is not None
    assert radio.metadata.images[0].path == "https://gfx.nrk.no/p1_troms-600"


def test_parse_radio_without_image() -> None:
    """A channel without posters still yields a Radio."""
    radio = parse_radio(make_channel("p1", "NRK P1", widths=()), INSTANCE_ID, DOMAIN)
    assert radio.name == "NRK P1"
    assert not radio.metadata.images


def test_parse_radio_never_carries_a_stream_url() -> None:
    """The manifest link must not leak onto the media item."""
    radio = parse_radio(make_channel("p1", "NRK P1"), INSTANCE_ID, DOMAIN)
    assert "manifest" not in str(radio.to_dict())
    assert "m3u8" not in str(radio.to_dict())
