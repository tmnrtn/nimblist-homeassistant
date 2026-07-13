"""Tests for the Nimblist data update coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nimblist.api import NimblistAuthError, NimblistConnectionError
from custom_components.nimblist.const import CONF_API_TOKEN, CONF_BASE_URL, DOMAIN
from custom_components.nimblist.coordinator import (
    NimblistDataUpdateCoordinator,
    NimblistPantryCoordinator,
)


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u1",
        data={CONF_BASE_URL: "https://nimblist.test", CONF_API_TOKEN: "nbl_t"},
    )
    entry.add_to_hass(hass)
    return entry


async def test_normalises_lists_and_excludes_templates(hass: HomeAssistant) -> None:
    client = AsyncMock()
    client.async_get_lists.return_value = [
        {
            "id": "l1",
            "name": "Groceries",
            "isTemplate": False,
            "items": [
                {"id": "i1", "name": "Milk", "isChecked": False},
                {"id": "i2", "name": "Eggs", "isChecked": True},
            ],
        },
        {"id": "t1", "name": "Template", "isTemplate": True, "items": []},
    ]
    coordinator = NimblistDataUpdateCoordinator(hass, _entry(hass), client)

    data = await coordinator._async_update_data()

    assert set(data) == {"l1"}  # template excluded
    assert data["l1"]["name"] == "Groceries"
    assert set(data["l1"]["items"]) == {"i1", "i2"}
    assert data["l1"]["items"]["i2"]["isChecked"] is True


async def test_auth_error_raises_config_entry_auth_failed(hass: HomeAssistant) -> None:
    client = AsyncMock()
    client.async_get_lists.side_effect = NimblistAuthError("nope")
    coordinator = NimblistDataUpdateCoordinator(hass, _entry(hass), client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_connection_error_raises_update_failed(hass: HomeAssistant) -> None:
    client = AsyncMock()
    client.async_get_lists.side_effect = NimblistConnectionError("down")
    coordinator = NimblistDataUpdateCoordinator(hass, _entry(hass), client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


# --- Pantry coordinator ---------------------------------------------------------------


async def test_pantry_normalises_to_id_map(hass: HomeAssistant) -> None:
    client = AsyncMock()
    client.async_get_pantry.return_value = [
        {"id": "p1", "name": "Butter", "quantity": "1 pack"},
        {"id": "p2", "name": "Milk", "quantity": None},
    ]
    coordinator = NimblistPantryCoordinator(hass, _entry(hass), client)

    data = await coordinator._async_update_data()

    assert set(data) == {"p1", "p2"}
    assert data["p1"]["name"] == "Butter"
    assert data["p2"]["quantity"] is None


async def test_pantry_auth_error_raises_config_entry_auth_failed(
    hass: HomeAssistant,
) -> None:
    client = AsyncMock()
    client.async_get_pantry.side_effect = NimblistAuthError("nope")
    coordinator = NimblistPantryCoordinator(hass, _entry(hass), client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_pantry_connection_error_raises_update_failed(
    hass: HomeAssistant,
) -> None:
    client = AsyncMock()
    client.async_get_pantry.side_effect = NimblistConnectionError("down")
    coordinator = NimblistPantryCoordinator(hass, _entry(hass), client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
