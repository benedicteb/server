"""Tests for the NRK Radio provider."""

from __future__ import annotations

import aiohttp
import pytest
from music_assistant_models.enums import MediaType
from music_assistant_models.errors import MediaNotFoundError, ProviderUnavailableError
from music_assistant_models.media_items import BrowseFolder, Radio

from music_assistant.providers.nrk_radio import NRKRadioProvider

from .conftest import CHANNELS, INSTANCE_ID, mock_api

ROOT = f"{INSTANCE_ID}://"


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
