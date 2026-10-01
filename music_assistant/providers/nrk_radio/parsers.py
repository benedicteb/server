"""Parsers turning NRK API payloads into Music Assistant objects."""

from __future__ import annotations

import re
from typing import Any, Final

from music_assistant_models.enums import ImageType
from music_assistant_models.media_items import MediaItemImage, ProviderMapping, Radio
from music_assistant_models.streamdetails import StreamMetadata

DISTRICT_CHANNEL_TYPE: Final = "districtChannel"
PREFERRED_IMAGE_WIDTH: Final = 600

# NRK serialises timestamps as "/Date(1790848772000+0200)/": epoch milliseconds plus an offset
_START_TIME_RE: Final = re.compile(r"/Date\((\d+)")


def is_district_channel(channel: dict[str, Any]) -> bool:
    """Return True if the channel is a regional variant of P1."""
    return channel.get("type") == DISTRICT_CHANNEL_TYPE


def select_image_url(channel: dict[str, Any]) -> str | None:
    """Return the square poster closest to the preferred width, or None if there is none."""
    posters = channel.get("_embedded", {}).get("playback", {}).get("squarePosters") or []
    items = [item for item in (posters[0].get("items") or []) if item.get("url")] if posters else []
    if not items:
        return None
    for item in items:
        if item.get("pixelWidth") == PREFERRED_IMAGE_WIDTH:
            return str(item["url"])
    return str(max(items, key=lambda item: item.get("pixelWidth") or 0)["url"])


def parse_radio(channel: dict[str, Any], instance_id: str, domain: str) -> Radio:
    """
    Build a Radio from an NRK channel entry.

    :param channel: Channel entry from NRK's live channel list.
    :param instance_id: Instance id of the provider the radio belongs to.
    :param domain: Domain of the provider the radio belongs to.
    """
    channel_id = str(channel["id"])
    title = channel.get("_embedded", {}).get("playback", {}).get("title")
    radio = Radio(
        item_id=channel_id,
        provider=instance_id,
        name=title or f"NRK {channel_id}",
        provider_mappings={
            ProviderMapping(
                item_id=channel_id,
                provider_domain=domain,
                provider_instance=instance_id,
            )
        },
    )
    if image_url := select_image_url(channel):
        radio.metadata.add_image(
            MediaItemImage(
                type=ImageType.THUMB,
                path=image_url,
                provider=instance_id,
                remotely_accessible=True,
            )
        )
    return radio


def select_stream_url(manifest: dict[str, Any]) -> str | None:
    """Return the HLS stream url from a playback manifest, or None if it is not playable."""
    if manifest.get("playability") != "playable":
        return None
    for asset in (manifest.get("playable") or {}).get("assets") or []:
        if asset.get("format") == "HLS" and asset.get("url"):
            return str(asset["url"])
    return None


def non_playable_reason(manifest: dict[str, Any]) -> str | None:
    """Return NRK's explanation for a manifest that is not playable, if it gives one."""
    message = (manifest.get("nonPlayable") or {}).get("endUserMessage")
    return str(message) if message else None


def parse_start_time(value: Any) -> int:
    """Return the epoch milliseconds of an NRK timestamp, or 0 if it cannot be parsed."""
    if not isinstance(value, str):
        return 0
    match = _START_TIME_RE.match(value)
    return int(match.group(1)) if match else 0


def select_current_element(elements: list[Any]) -> dict[str, Any] | None:
    """Return the entry currently on air, or None if nothing is marked as current."""
    present = [
        element
        for element in elements
        if isinstance(element, dict) and element.get("relativeTimeType") == "Present"
    ]
    if not present:
        return None
    # the feed is not ordered and can mark several entries as current at once
    return max(present, key=lambda element: parse_start_time(element.get("startTime")))


def parse_stream_metadata(elements: list[Any]) -> StreamMetadata | None:
    """Return now-playing metadata for a channel's live elements, or None if nothing is current."""
    element = select_current_element(elements)
    if element is None or not (title := element.get("title")):
        return None
    if element.get("type") == "Music":
        return StreamMetadata(
            title=str(title),
            artist=element.get("description") or None,
            image_url=element.get("imageUrl") or None,
        )
    return StreamMetadata(title=str(title), artist=element.get("programTitle") or None)
