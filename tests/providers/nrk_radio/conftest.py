"""Shared fixtures for the NRK Radio provider tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from music_assistant.providers.nrk_radio import API_BASE, SUPPORTED_FEATURES, NRKRadioProvider
from tests.common import use_real_create_task

INSTANCE_ID = "nrk_radio--test123"
DOMAIN = "nrk_radio"


def make_channel(
    channel_id: str,
    title: str,
    channel_type: str = "regionalChannel",
    *,
    widths: tuple[int, ...] = (300, 600, 960),
) -> dict[str, Any]:
    """Build a channel entry as returned by NRK's /radio/live."""
    playback: dict[str, Any] = {"title": title, "description": "", "isGeoBlocked": False}
    if widths:
        playback["squarePosters"] = [
            {
                "ratio": "1:1",
                "items": [
                    {"url": f"https://gfx.nrk.no/{channel_id}-{width}", "pixelWidth": width}
                    for width in widths
                ],
            }
        ]
    return {
        "_links": {"manifest": {"href": f"/playback/manifest/channel/{channel_id}"}},
        "type": channel_type,
        "id": channel_id,
        "_embedded": {"playback": playback},
    }


CHANNELS: list[dict[str, Any]] = [
    make_channel("p1", "NRK P1"),
    make_channel("p3", "NRK P3"),
    make_channel("sapmi", "NRK Sámi radio"),
    make_channel("p1_troms", "NRK P1 Troms", "districtChannel"),
    make_channel("p1_more_romsdal", "NRK P1 Møre og Romsdal", "districtChannel"),
]

STREAM_URL = "https://nrk-live-radio-world.akamaized.net/p1/muxed.m3u8?adap=audio&aco=aac"

MANIFEST_PLAYABLE: dict[str, Any] = {
    "id": "p1",
    "playability": "playable",
    "streamingMode": "live",
    "playable": {
        "assets": [
            {
                "url": STREAM_URL,
                "format": "HLS",
                "mimeType": "application/vnd.apple.mpegurl",
                "encrypted": False,
            }
        ],
        "liveBuffer": {"bufferDuration": "PT3H", "bufferType": "sliding"},
    },
    "nonPlayable": None,
}

MANIFEST_NOT_PLAYABLE: dict[str, Any] = {
    "id": "p1",
    "playability": "nonPlayable",
    "playable": None,
    "nonPlayable": {"reason": "blocked", "endUserMessage": "Ikke tilgjengelig utenfor Norge"},
}


def make_element(
    title: str,
    *,
    artist: str = "",
    program: str = "Siesta",
    kind: str = "Music",
    relative: str = "Past",
    start_ms: int | None = 1790848772000,
    image: str | None = None,
) -> dict[str, Any]:
    """Build an entry as returned by NRK's /channels/{id}/liveelements."""
    return {
        "title": title,
        "description": artist,
        "programId": "IUFL23016926",
        "channelId": "p3",
        "startTime": None if start_ms is None else f"/Date({start_ms}+0200)/",
        "duration": "PT3M",
        "type": kind,
        "imageUrl": image,
        "programTitle": program,
        "relativeTimeType": relative,
    }


@pytest.fixture
def provider() -> NRKRadioProvider:
    """Return an NRKRadioProvider with mocked dependencies and a cold cache."""
    mass = AsyncMock()
    mass.http_session = MagicMock()
    # force a cache miss so the wrapped fetch always runs
    mass.cache.get_with_freshness = AsyncMock(return_value=(None, False, False))
    use_real_create_task(mass)
    manifest = MagicMock()
    manifest.domain = DOMAIN
    config = MagicMock()
    config.instance_id = INSTANCE_ID
    config.get_value.return_value = "GLOBAL"
    return NRKRadioProvider(mass, manifest, config, SUPPORTED_FEATURES)


def mock_api(provider: NRKRadioProvider, routes: dict[str, Any]) -> MagicMock:
    """
    Make the provider's HTTP session answer from a table of API paths.

    :param provider: Provider whose session is replaced.
    :param routes: API path mapped to the JSON payload to return, or an exception to raise.
    """

    def _get(url: str, **_: Any) -> MagicMock:
        result = routes[url.removeprefix(API_BASE)]
        context = MagicMock()
        if isinstance(result, Exception):
            context.__aenter__ = AsyncMock(side_effect=result)
        else:
            response = MagicMock()
            response.raise_for_status = MagicMock()
            response.json = AsyncMock(return_value=result)
            context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        return context

    get = MagicMock(side_effect=_get)
    provider.mass.http_session.get = get  # type: ignore[method-assign]
    return get
