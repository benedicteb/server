"""Tests for the NRK Radio payload parsers."""

from __future__ import annotations

from music_assistant.providers.nrk_radio.parsers import (
    is_district_channel,
    non_playable_reason,
    parse_radio,
    parse_start_time,
    parse_stream_metadata,
    select_current_element,
    select_image_url,
    select_stream_url,
)

from .conftest import (
    DOMAIN,
    INSTANCE_ID,
    MANIFEST_NOT_PLAYABLE,
    MANIFEST_PLAYABLE,
    STREAM_URL,
    make_channel,
    make_element,
)


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


def test_select_stream_url() -> None:
    """A playable manifest yields its HLS asset url."""
    assert select_stream_url(MANIFEST_PLAYABLE) == STREAM_URL


def test_select_stream_url_not_playable() -> None:
    """A manifest that is not playable yields no url."""
    assert select_stream_url(MANIFEST_NOT_PLAYABLE) is None


def test_select_stream_url_without_hls_asset() -> None:
    """A playable manifest without an HLS asset yields no url."""
    manifest = {"playability": "playable", "playable": {"assets": []}}
    assert select_stream_url(manifest) is None
    manifest = {"playability": "playable", "playable": {"assets": [{"format": "DASH", "url": "x"}]}}
    assert select_stream_url(manifest) is None


def test_non_playable_reason() -> None:
    """NRK's own explanation is returned when present."""
    assert non_playable_reason(MANIFEST_NOT_PLAYABLE) == "Ikke tilgjengelig utenfor Norge"
    assert non_playable_reason(MANIFEST_PLAYABLE) is None
    assert non_playable_reason({"nonPlayable": {"reason": "blocked"}}) is None


def test_parse_start_time() -> None:
    """The epoch milliseconds are extracted from NRK's date format."""
    assert parse_start_time("/Date(1790848772000+0200)/") == 1790848772000


def test_parse_start_time_unparseable() -> None:
    """Missing or malformed start times sort as oldest."""
    assert parse_start_time(None) == 0
    assert parse_start_time("") == 0
    assert parse_start_time("2026-10-01T12:00:00") == 0
    assert parse_start_time(12345) == 0


def test_select_current_element_takes_latest_present() -> None:
    """With several Present entries, the one that started last wins, regardless of order."""
    elements = [
        make_element("Older", relative="Present", start_ms=2000),
        make_element("Past song", relative="Past", start_ms=9000),
        make_element("Newer", relative="Present", start_ms=3000),
        make_element("No start", relative="Present", start_ms=None),
    ]
    current = select_current_element(elements)
    assert current is not None
    assert current["title"] == "Newer"


def test_select_current_element_none_present() -> None:
    """Without a Present entry there is no current element."""
    assert select_current_element([make_element("A"), make_element("B")]) is None
    assert select_current_element([]) is None


def test_select_current_element_ignores_non_dict_entries() -> None:
    """Entries that are not objects are skipped."""
    assert select_current_element([None, "x", 3]) is None


def test_parse_stream_metadata_music() -> None:
    """A song maps to title, artist and artwork."""
    elements = [
        make_element(
            "Memoarer",
            artist="Undergrunn",
            relative="Present",
            image="https://gfx.nrk.no/cover",
        )
    ]
    metadata = parse_stream_metadata(elements)
    assert metadata is not None
    assert metadata.title == "Memoarer"
    assert metadata.artist == "Undergrunn"
    assert metadata.image_url == "https://gfx.nrk.no/cover"


def test_parse_stream_metadata_music_without_artist_or_image() -> None:
    """An empty artist or missing artwork becomes None, not an empty string."""
    metadata = parse_stream_metadata([make_element("Instrumental", relative="Present")])
    assert metadata is not None
    assert metadata.artist is None
    assert metadata.image_url is None


def test_parse_stream_metadata_speech() -> None:
    """A speech segment shows the segment title with the programme as artist line."""
    elements = [
        make_element("Åpen prat", kind="News", program="Siesta", relative="Present"),
    ]
    metadata = parse_stream_metadata(elements)
    assert metadata is not None
    assert metadata.title == "Åpen prat"
    assert metadata.artist == "Siesta"
    assert metadata.image_url is None


def test_parse_stream_metadata_nothing_current() -> None:
    """No Present entry, or one without a title, yields no metadata."""
    assert parse_stream_metadata([make_element("Past song")]) is None
    assert parse_stream_metadata([make_element("", relative="Present")]) is None


def test_parse_radio_with_null_embedded_data() -> None:
    """A channel whose embedded playback data is null still yields a Radio."""
    for channel in (
        {"id": "p1", "type": "regionalChannel", "_embedded": None},
        {"id": "p1", "type": "regionalChannel", "_embedded": {"playback": None}},
    ):
        radio = parse_radio(channel, INSTANCE_ID, DOMAIN)
        assert radio.name == "NRK p1"
        assert not radio.metadata.images
