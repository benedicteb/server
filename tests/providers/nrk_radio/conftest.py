"""Shared fixtures for the NRK Radio provider tests."""

from __future__ import annotations

from typing import Any

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
