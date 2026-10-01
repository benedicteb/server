"""NRK Radio music provider."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

import aiohttp
from music_assistant_models.enums import MediaType, ProviderFeature
from music_assistant_models.errors import MediaNotFoundError, ProviderUnavailableError
from music_assistant_models.media_items import (
    BrowseFolder,
    MediaItemType,
    Radio,
    SearchResults,
)

from music_assistant.controllers.cache import use_cache
from music_assistant.models.music_provider import MusicProvider

from .parsers import is_district_channel, parse_radio

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ConfigEntry, ProviderConfig
    from music_assistant_models.provider import ProviderManifest

    from music_assistant.mass import MusicAssistant
    from music_assistant.models import ProviderInstanceType

API_BASE: Final = "https://psapi.nrk.no"

# bound each request; the shared session's default timeout is too long for a metadata fetch
HTTP_TIMEOUT: Final = aiohttp.ClientTimeout(total=10)

CHANNEL_CACHE_EXPIRATION: Final = 3600 * 24
DISTRICT_FOLDER_ID: Final = "district"

SUPPORTED_FEATURES = {
    ProviderFeature.BROWSE,
    ProviderFeature.SEARCH,
}


async def setup(
    mass: MusicAssistant, manifest: ProviderManifest, config: ProviderConfig
) -> ProviderInstanceType:
    """Initialize provider(instance) with given configuration."""
    return NRKRadioProvider(mass, manifest, config, SUPPORTED_FEATURES)


class NRKRadioProvider(MusicProvider):
    """NRK Radio music provider."""

    @property
    def max_concurrent_streams(self) -> None:
        """Allow unlimited concurrent upstream source streams."""
        return None

    async def get_config_entries(self) -> tuple[ConfigEntry, ...]:
        """Return Config entries to configure this provider (none required)."""
        return ()

    async def browse(self, path: str) -> Sequence[MediaItemType | BrowseFolder]:
        """
        Browse NRK's live channels.

        :param path: The browse path, with the district folder as its only sub-path.
        """
        subpath = path.split("://", 1)[1] if "://" in path else ""
        channels = await self._get_channels()
        if subpath == DISTRICT_FOLDER_ID:
            return [
                self._parse_radio(channel) for channel in channels if is_district_channel(channel)
            ]
        if subpath:
            msg = f"Invalid subpath: {subpath}"
            raise KeyError(msg)
        items: list[MediaItemType | BrowseFolder] = [
            self._parse_radio(channel) for channel in channels if not is_district_channel(channel)
        ]
        items.append(
            BrowseFolder(
                item_id=DISTRICT_FOLDER_ID,
                provider=self.instance_id,
                path=f"{path}{DISTRICT_FOLDER_ID}",
                name="P1 district channels",
                translation_key="p1_district_channels",
            )
        )
        return items

    async def get_radio(self, prov_radio_id: str) -> Radio:
        """Get full radio details by id."""
        if channel := await self._get_channel(prov_radio_id):
            return self._parse_radio(channel)
        raise MediaNotFoundError(f"Radio station {prov_radio_id} not found")

    async def search(
        self,
        search_query: str,
        media_types: list[MediaType],
        limit: int = 5,
    ) -> SearchResults:
        """
        Search NRK channels by name.

        :param search_query: Text to look for in channel titles.
        :param media_types: Media types to search; empty means all.
        :param limit: Maximum number of results.
        """
        if media_types and MediaType.RADIO not in media_types:
            return SearchResults()
        query = search_query.strip().casefold()
        radios = [
            radio
            for channel in await self._get_channels()
            if query in (radio := self._parse_radio(channel)).name.casefold()
        ][:limit]
        return SearchResults(radio=radios)

    @use_cache(CHANNEL_CACHE_EXPIRATION)
    async def _get_channels(self) -> list[dict[str, Any]]:
        """Fetch the list of NRK's live radio channels."""
        channels: list[dict[str, Any]] = await self._get_json("/radio/live")
        return channels

    async def _get_channel(self, channel_id: str) -> dict[str, Any] | None:
        """Return the channel entry for an id, or None if unknown."""
        return next(
            (channel for channel in await self._get_channels() if channel.get("id") == channel_id),
            None,
        )

    async def _get_json(self, path: str) -> Any:
        """
        Fetch a JSON document from NRK's API.

        :param path: API path, starting with a slash.
        """
        try:
            async with self.mass.http_session.get(
                f"{API_BASE}{path}", timeout=HTTP_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ProviderUnavailableError("NRK Radio API unavailable") from err

    def _parse_radio(self, channel: dict[str, Any]) -> Radio:
        """Build a Radio for a channel entry."""
        return parse_radio(channel, self.instance_id, self.domain)
