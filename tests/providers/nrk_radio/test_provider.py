"""Tests for the NRK Radio provider."""

from __future__ import annotations

import pytest
from music_assistant_models.enums import ContentType, MediaType, StreamType
from music_assistant_models.errors import UnplayableMediaError
from music_assistant_models.media_items import BrowseFolder, Radio

from music_assistant.providers.nrk_radio import METADATA_UPDATE_INTERVAL, NRKRadioProvider

from .conftest import (
    CHANNELS,
    INSTANCE_ID,
    MANIFEST_NOT_PLAYABLE,
    MANIFEST_PLAYABLE,
    STREAM_URL,
    make_channel,
    make_element,
    mock_api,
)

ROOT = f"{INSTANCE_ID}://"
MANIFEST_PATH = "/playback/manifest/channel/p1"
ELEMENTS_PATH = "/channels/p1/liveelements"
NOW_PLAYING = [
    make_element("Old song", artist="Someone", relative="Past", start_ms=1000),
    make_element("Memoarer", artist="Undergrunn", relative="Present", start_ms=2000),
]


async def test_browse(provider: NRKRadioProvider) -> None:
    """The root shows national channels and the district folder, which holds the rest."""
    mock_api(provider, {"/radio/live": CHANNELS})

    items = await provider.browse(ROOT)

    assert [item.item_id for item in items] == ["p1", "p3", "sapmi", "district"]
    assert all(isinstance(item, Radio) for item in items[:3])
    folder = items[3]
    assert isinstance(folder, BrowseFolder)
    assert folder.name == "Local channels"
    assert folder.translation_key == "local_channels"

    district = await provider.browse(folder.path)
    assert [item.item_id for item in district] == ["p1_troms", "p1_more_romsdal"]


async def test_search(provider: NRKRadioProvider) -> None:
    """Search matches channel titles by case-folded substring."""
    mock_api(provider, {"/radio/live": CHANNELS})

    results = await provider.search("SÁMI", [MediaType.RADIO], limit=10)
    assert [radio.item_id for radio in results.radio] == ["sapmi"]

    results = await provider.search("nrk", [MediaType.TRACK], limit=10)
    assert not results.radio

    results = await provider.search("  ", [MediaType.RADIO], limit=10)
    assert not results.radio


async def test_stream_details(provider: NRKRadioProvider) -> None:
    """A playable channel yields HLS stream details without waiting for now-playing info."""
    get = mock_api(provider, {"/radio/live": CHANNELS, MANIFEST_PATH: MANIFEST_PLAYABLE})

    details = await provider.get_stream_details("p1", MediaType.RADIO)

    assert details.path == STREAM_URL
    assert details.stream_type == StreamType.HLS
    assert details.audio_format.content_type == ContentType.AAC
    assert details.stream_metadata_update_interval == METADATA_UPDATE_INTERVAL
    assert details.stream_metadata is None
    assert get.call_count == 2


async def test_stream_details_not_playable(provider: NRKRadioProvider) -> None:
    """A channel NRK reports as not playable fails with NRK's own message."""
    mock_api(provider, {"/radio/live": CHANNELS, MANIFEST_PATH: MANIFEST_NOT_PLAYABLE})
    with pytest.raises(UnplayableMediaError, match="Ikke tilgjengelig utenfor Norge"):
        await provider.get_stream_details("p1", MediaType.RADIO)


async def test_metadata_update(provider: NRKRadioProvider) -> None:
    """The callback shows what is on air, and a failed fetch leaves the display untouched."""
    mock_api(
        provider,
        {"/radio/live": CHANNELS, MANIFEST_PATH: MANIFEST_PLAYABLE, ELEMENTS_PATH: NOW_PLAYING},
    )
    details = await provider.get_stream_details("p1", MediaType.RADIO)
    assert details.stream_metadata_update_callback is not None

    await details.stream_metadata_update_callback(details, 0)
    assert details.stream_metadata is not None
    assert details.stream_metadata.title == "Memoarer"

    mock_api(provider, {ELEMENTS_PATH: TimeoutError()})
    await details.stream_metadata_update_callback(details, 30)
    assert details.stream_metadata is not None
    assert details.stream_metadata.title == "Memoarer"


async def test_unusable_channel_entries_are_dropped(provider: NRKRadioProvider) -> None:
    """Entries that cannot be turned into a radio are skipped instead of breaking every listing."""
    bad_posters = make_channel("bad_posters", "Bad posters")
    bad_posters["_embedded"]["playback"]["squarePosters"] = [None]
    payload = [*CHANNELS, None, {"type": "regionalChannel"}, {"id": 7}, bad_posters]
    mock_api(provider, {"/radio/live": payload})

    items = await provider.browse(ROOT)

    assert [item.item_id for item in items] == ["p1", "p3", "sapmi", "district"]
