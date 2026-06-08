"""The Nimblist integration.

Exposes a user's Nimblist shopping lists as Home Assistant ``todo`` entities.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NimblistApiClient
from .const import CONF_API_TOKEN, CONF_BASE_URL
from .coordinator import NimblistDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.TODO]

type NimblistConfigEntry = ConfigEntry[NimblistDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: NimblistConfigEntry) -> bool:
    """Set up Nimblist from a config entry."""
    client = NimblistApiClient(
        entry.data[CONF_BASE_URL],
        entry.data[CONF_API_TOKEN],
        async_get_clientsession(hass),
    )
    coordinator = NimblistDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NimblistConfigEntry) -> bool:
    """Unload a Nimblist config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_on_update(hass: HomeAssistant, entry: NimblistConfigEntry) -> None:
    """Reload the entry when options (e.g. the scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)
