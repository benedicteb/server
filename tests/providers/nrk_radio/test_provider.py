"""Tests for the NRK Radio provider."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock

import aiohttp
import pytest
from music_assistant_models.enums import ContentType, MediaType, StreamType
from music_assistant_models.errors import MediaNotFoundError, ProviderUnavailableError
from music_assistant_models.media_items import BrowseFolder, Radio
from music_assistant_models.streamdetails import StreamDetails, StreamMetadata

from music_assistant.providers.nrk_radio import METADATA_UPDATE_INTERVAL, NRKRadioProvider

from .conftest import (
    CHANNELS,
    INSTANCE_ID,
    MANIFEST_NOT_PLAYABLE,
    MANIFEST_PLAYABLE,
    STREAM_URL,
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


async def test_browse_root_lists_national_channels_then_district_folder(
    provider: NRKRadioProvider,
) -> None:
    """The root shows national channels in NRK's order, then the district folder."""
    mock_api(provider, {"/radio/live": CHANNELS})

    items = await provider.browse(ROOT)

    assert [item.item_id for item in items] == ["p1", "p3", "sapmi", "district"]
    assert all(isinstance(item, Radio) for item in items[:3])
    folder = items[3]
    assert isinstance(folder, BrowseFolder)
    assert folder.path == f"{ROOT}district"
    assert folder.name == "Distriktskanaler"
    assert folder.translation_key == "p1_district_channels"


async def test_browse_district_folder(provider: NRKRadioProvider) -> None:
    """The district folder lists only the district channels."""
    mock_api(provider, {"/radio/live": CHANNELS})

    items = await provider.browse(f"{ROOT}district")

    assert [item.item_id for item in items] == ["p1_troms", "p1_more_romsdal"]
    assert all(isinstance(item, Radio) for item in items)


async def test_browse_unknown_subpath(provider: NRKRadioProvider) -> None:
    """Any other sub-path is rejected."""
    mock_api(provider, {"/radio/live": CHANNELS})
    with pytest.raises(KeyError):
        await provider.browse(f"{ROOT}nope")


async def test_browse_when_api_is_down(provider: NRKRadioProvider) -> None:
    """A failed channel list request surfaces as provider unavailable."""
    mock_api(provider, {"/radio/live": aiohttp.ClientError("down")})
    with pytest.raises(ProviderUnavailableError):
        await provider.browse(ROOT)


async def test_browse_when_api_times_out(provider: NRKRadioProvider) -> None:
    """A timeout surfaces as provider unavailable."""
    mock_api(provider, {"/radio/live": TimeoutError()})
    with pytest.raises(ProviderUnavailableError):
        await provider.browse(ROOT)


async def test_channel_list_request_uses_timeout(provider: NRKRadioProvider) -> None:
    """Requests are bounded to ten seconds."""
    get = mock_api(provider, {"/radio/live": CHANNELS})
    await provider.browse(ROOT)
    assert get.call_args.kwargs["timeout"].total == 10


async def test_get_radio(provider: NRKRadioProvider) -> None:
    """A known channel id resolves to its Radio."""
    mock_api(provider, {"/radio/live": CHANNELS})
    radio = await provider.get_radio("p1_troms")
    assert radio.name == "NRK P1 Troms"


async def test_get_radio_unknown(provider: NRKRadioProvider) -> None:
    """An unknown channel id is not found."""
    mock_api(provider, {"/radio/live": CHANNELS})
    with pytest.raises(MediaNotFoundError):
        await provider.get_radio("nope")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("p3", ["p3"]),
        ("SÁMI", ["sapmi"]),
        ("møre", ["p1_more_romsdal"]),
        ("  troms ", ["p1_troms"]),
        ("nrk p1", ["p1", "p1_troms", "p1_more_romsdal"]),
        ("zzz", []),
    ],
)
async def test_search(provider: NRKRadioProvider, query: str, expected: list[str]) -> None:
    """Search matches channel titles by case-folded substring."""
    mock_api(provider, {"/radio/live": CHANNELS})
    results = await provider.search(query, [MediaType.RADIO], limit=10)
    assert [radio.item_id for radio in results.radio] == expected


async def test_search_respects_limit(provider: NRKRadioProvider) -> None:
    """No more than limit results are returned."""
    mock_api(provider, {"/radio/live": CHANNELS})
    results = await provider.search("nrk", [MediaType.RADIO], limit=2)
    assert len(results.radio) == 2


async def test_search_without_media_types_includes_radio(provider: NRKRadioProvider) -> None:
    """An empty media type list means everything, radio included."""
    mock_api(provider, {"/radio/live": CHANNELS})
    results = await provider.search("p3", [], limit=5)
    assert [radio.item_id for radio in results.radio] == ["p3"]


async def test_search_for_other_media_types_skips_the_api(provider: NRKRadioProvider) -> None:
    """A search that does not ask for radio returns nothing and makes no request."""
    get = mock_api(provider, {"/radio/live": CHANNELS})
    results = await provider.search("p3", [MediaType.TRACK], limit=5)
    assert not results.radio
    get.assert_not_called()


async def test_stream_details(provider: NRKRadioProvider) -> None:
    """A playable channel yields HLS stream details with the first now-playing info."""
    mock_api(
        provider,
        {"/radio/live": CHANNELS, MANIFEST_PATH: MANIFEST_PLAYABLE, ELEMENTS_PATH: NOW_PLAYING},
    )

    details = await provider.get_stream_details("p1", MediaType.RADIO)

    assert details.path == STREAM_URL
    assert details.provider == INSTANCE_ID
    assert details.item_id == "p1"
    assert details.media_type == MediaType.RADIO
    assert details.stream_type == StreamType.HLS
    assert details.audio_format.content_type == ContentType.AAC
    assert details.can_seek is False
    assert details.allow_seek is False
    assert details.stream_metadata_update_interval == METADATA_UPDATE_INTERVAL
    assert details.stream_metadata_update_callback is not None
    assert details.stream_metadata is not None
    assert details.stream_metadata.title == "Memoarer"
    assert details.stream_metadata.artist == "Undergrunn"


async def test_stream_details_survive_now_playing_failure(provider: NRKRadioProvider) -> None:
    """Playback still starts when the now-playing feed is down."""
    mock_api(
        provider,
        {
            "/radio/live": CHANNELS,
            MANIFEST_PATH: MANIFEST_PLAYABLE,
            ELEMENTS_PATH: aiohttp.ClientError("down"),
        },
    )
    details = await provider.get_stream_details("p1", MediaType.RADIO)
    assert details.path == STREAM_URL
    assert details.stream_metadata is None


async def test_stream_details_unknown_channel(provider: NRKRadioProvider) -> None:
    """An unknown channel id is not found, without asking for a manifest."""
    get = mock_api(provider, {"/radio/live": CHANNELS})
    with pytest.raises(MediaNotFoundError):
        await provider.get_stream_details("nope", MediaType.RADIO)
    assert get.call_count == 1


async def test_stream_details_not_playable(provider: NRKRadioProvider) -> None:
    """A channel NRK reports as not playable fails with NRK's own message."""
    mock_api(provider, {"/radio/live": CHANNELS, MANIFEST_PATH: MANIFEST_NOT_PLAYABLE})
    with pytest.raises(MediaNotFoundError, match="Ikke tilgjengelig utenfor Norge"):
        await provider.get_stream_details("p1", MediaType.RADIO)


async def test_stream_details_without_hls_asset(provider: NRKRadioProvider) -> None:
    """A playable manifest without an HLS asset is reported as not found."""
    manifest = {"playability": "playable", "playable": {"assets": []}}
    mock_api(provider, {"/radio/live": CHANNELS, MANIFEST_PATH: manifest})
    with pytest.raises(MediaNotFoundError):
        await provider.get_stream_details("p1", MediaType.RADIO)


async def test_stream_details_manifest_request_fails(provider: NRKRadioProvider) -> None:
    """A failed manifest request surfaces as provider unavailable."""
    mock_api(provider, {"/radio/live": CHANNELS, MANIFEST_PATH: aiohttp.ClientError("down")})
    with pytest.raises(ProviderUnavailableError):
        await provider.get_stream_details("p1", MediaType.RADIO)


async def _playing(provider: NRKRadioProvider) -> StreamDetails:
    """Return stream details for P1 as they are while it plays."""
    mock_api(
        provider,
        {"/radio/live": CHANNELS, MANIFEST_PATH: MANIFEST_PLAYABLE, ELEMENTS_PATH: NOW_PLAYING},
    )
    return await provider.get_stream_details("p1", MediaType.RADIO)


async def test_metadata_update_picks_up_new_song(provider: NRKRadioProvider) -> None:
    """The callback replaces the metadata with the entry now on air."""
    details = await _playing(provider)
    newer = [
        *NOW_PLAYING,
        make_element("Åpen prat", kind="News", relative="Present", start_ms=3000),
    ]
    mock_api(provider, {ELEMENTS_PATH: newer})

    assert details.stream_metadata_update_callback is not None
    await details.stream_metadata_update_callback(details, 30)

    assert details.stream_metadata == StreamMetadata(title="Åpen prat", artist="Siesta")


async def test_metadata_update_clears_when_nothing_is_current(provider: NRKRadioProvider) -> None:
    """With no current entry the metadata is cleared so the station name shows."""
    details = await _playing(provider)
    mock_api(provider, {ELEMENTS_PATH: [make_element("Past song")]})

    assert details.stream_metadata_update_callback is not None
    await details.stream_metadata_update_callback(details, 30)

    assert details.stream_metadata is None


async def test_metadata_update_keeps_display_when_request_fails(
    provider: NRKRadioProvider,
) -> None:
    """A failed fetch leaves the current display untouched."""
    details = await _playing(provider)
    mock_api(provider, {ELEMENTS_PATH: TimeoutError()})

    assert details.stream_metadata_update_callback is not None
    await details.stream_metadata_update_callback(details, 30)

    assert details.stream_metadata is not None
    assert details.stream_metadata.title == "Memoarer"


async def test_metadata_update_keeps_display_on_malformed_payload(
    provider: NRKRadioProvider,
) -> None:
    """A payload that is not a list counts as a failed fetch."""
    details = await _playing(provider)
    mock_api(provider, {ELEMENTS_PATH: {"message": "error", "statusCode": 500}})

    assert details.stream_metadata_update_callback is not None
    await details.stream_metadata_update_callback(details, 30)

    assert details.stream_metadata is not None
    assert details.stream_metadata.title == "Memoarer"


@pytest.mark.parametrize("payload", [{"message": "error", "statusCode": 500}, [], None, "oops"])
async def test_malformed_channel_list_is_unavailable_and_not_cached(
    provider: NRKRadioProvider, payload: Any
) -> None:
    """A channel list of the wrong shape is an outage, and must not stick in the cache."""
    mock_api(provider, {"/radio/live": payload})

    with pytest.raises(ProviderUnavailableError):
        await provider.browse(ROOT)

    await asyncio.sleep(0)
    cast("AsyncMock", provider.mass.cache.set).assert_not_called()


async def test_unusable_channel_entries_are_dropped(provider: NRKRadioProvider) -> None:
    """Entries without a usable id are skipped instead of breaking every listing."""
    payload = [*CHANNELS, None, "x", {"type": "regionalChannel"}, {"id": 7}, {"id": ""}]
    mock_api(provider, {"/radio/live": payload})

    items = await provider.browse(ROOT)

    assert [item.item_id for item in items] == ["p1", "p3", "sapmi", "district"]


async def test_channel_list_is_served_from_cache(provider: NRKRadioProvider) -> None:
    """A cached channel list is used without asking NRK again."""
    get = mock_api(provider, {"/radio/live": CHANNELS})
    provider.mass.cache.get_with_freshness = AsyncMock(  # type: ignore[method-assign]
        return_value=(CHANNELS, True, True)
    )

    items = await provider.browse(ROOT)

    assert [item.item_id for item in items] == ["p1", "p3", "sapmi", "district"]
    get.assert_not_called()


async def test_channel_list_is_cached_for_a_day(provider: NRKRadioProvider) -> None:
    """The fetched channel list is stored with a 24-hour expiry."""
    mock_api(provider, {"/radio/live": CHANNELS})

    await provider.browse(ROOT)
    await asyncio.sleep(0)

    cache_set = cast("AsyncMock", provider.mass.cache.set)
    cache_set.assert_called_once()
    assert cache_set.call_args.kwargs["expiration"] == 86400
    assert cache_set.call_args.kwargs["data"] == CHANNELS
