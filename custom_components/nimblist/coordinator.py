"""Data update coordinator for the Nimblist integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NimblistApiClient, NimblistAuthError, NimblistError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Normalised shape: {list_id: {"id", "name", "items": {item_id: item_dict}}}
type NimblistData = dict[str, dict[str, Any]]

# Normalised pantry shape: {item_id: item_dict}
type NimblistPantryData = dict[str, dict[str, Any]]


class NimblistDataUpdateCoordinator(DataUpdateCoordinator[NimblistData]):
    """Polls Nimblist and exposes the user's active lists (templates excluded)."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: NimblistApiClient
    ) -> None:
        """Initialise the coordinator."""
        self.client = client
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )

    async def _async_update_data(self) -> NimblistData:
        """Fetch every list (with items) and normalise it."""
        try:
            lists = await self.client.async_get_lists()
        except NimblistAuthError as err:
            # Triggers Home Assistant's reauth flow.
            raise ConfigEntryAuthFailed(str(err)) from err
        except NimblistError as err:
            raise UpdateFailed(str(err)) from err

        result: NimblistData = {}
        for lst in lists:
            if lst.get("isTemplate"):
                continue
            list_id = lst["id"]
            result[list_id] = {
                "id": list_id,
                "name": lst.get("name") or "Shopping list",
                "items": {item["id"]: item for item in lst.get("items") or []},
            }
        return result


class NimblistPantryCoordinator(DataUpdateCoordinator[NimblistPantryData]):
    """Polls the household pantry and exposes it keyed by item id.

    Kept separate from :class:`NimblistDataUpdateCoordinator` so the pantry entities
    fail/refresh independently of the shopping-list entities (lower blast radius).
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: NimblistApiClient
    ) -> None:
        """Initialise the pantry coordinator (shares the entry's scan interval)."""
        self.client = client
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_pantry",
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )

    async def _async_update_data(self) -> NimblistPantryData:
        """Fetch the pantry and normalise it to ``{item_id: item_dict}``."""
        try:
            items = await self.client.async_get_pantry()
        except NimblistAuthError as err:
            # Triggers Home Assistant's reauth flow.
            raise ConfigEntryAuthFailed(str(err)) from err
        except NimblistError as err:
            raise UpdateFailed(str(err)) from err

        return {item["id"]: item for item in items}
