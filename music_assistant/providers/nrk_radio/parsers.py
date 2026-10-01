"""Parsers turning NRK API payloads into Music Assistant objects."""

from __future__ import annotations

from typing import Any, Final

from music_assistant_models.enums import ImageType
from music_assistant_models.media_items import MediaItemImage, ProviderMapping, Radio

DISTRICT_CHANNEL_TYPE: Final = "districtChannel"
PREFERRED_IMAGE_WIDTH: Final = 600


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
