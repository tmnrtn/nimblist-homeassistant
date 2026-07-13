"""Tests for the Nimblist pantry "expiring soon" sensor."""

from __future__ import annotations

from typing import Any

from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nimblist.const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_EXPIRY_WINDOW_DAYS,
    DOMAIN,
)

BASE = "https://nimblist.test"
LISTS_URL = f"{BASE}/api/shoppinglists"
PANTRY_URL = f"{BASE}/api/pantry"
ENTITY_ID = "sensor.pantry_expiring_soon"

# Frozen "now" for deterministic use-by windows.
FROZEN_NOW = "2026-07-13T12:00:00+00:00"


def _pantry_payload() -> list[dict[str, Any]]:
    return [
        # 2 days out → inside the default 7-day window.
        {
            "id": "p1",
            "name": "Butter",
            "quantity": "1 pack",
            "categoryName": "Dairy",
            "estimatedUseBy": "2026-07-15T00:00:00+00:00",
            "useBySource": "foodkeeper",
            "useByMatchedName": "Butter, salted",
        },
        # 12 days out → outside the default 7-day window (but inside 14).
        {
            "id": "p2",
            "name": "Flour",
            "quantity": "500g",
            "categoryName": "Baking",
            "estimatedUseBy": "2026-07-25T00:00:00+00:00",
            "useBySource": "foodkeeper",
            "useByMatchedName": "Flour, white",
        },
        # No estimate → never counted.
        {
            "id": "p3",
            "name": "Salt",
            "quantity": None,
            "categoryName": "Baking",
            "estimatedUseBy": None,
            "useBySource": None,
            "useByMatchedName": None,
        },
        # Already past its estimate → counts as expiring.
        {
            "id": "p4",
            "name": "Yoghurt",
            "quantity": "2 pots",
            "categoryName": "Dairy",
            "estimatedUseBy": "2026-07-10T00:00:00+00:00",
            "useBySource": "foodkeeper",
            "useByMatchedName": "Yoghurt, plain",
        },
    ]


async def _setup(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    *,
    options: dict[str, Any] | None = None,
) -> MockConfigEntry:
    aioclient_mock.get(LISTS_URL, json=[])
    aioclient_mock.get(PANTRY_URL, json=_pantry_payload())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u1",
        data={CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_t"},
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@freeze_time(FROZEN_NOW)
async def test_sensor_counts_items_within_default_window(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    # p1 (2 days) + p4 (already past) = 2; p2 (12 days) and p3 (no estimate) excluded.
    assert state.state == "2"


@freeze_time(FROZEN_NOW)
async def test_sensor_attributes_list_expiring_items(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["window_days"] == 7
    items = state.attributes["items"]
    names = {i["name"] for i in items}
    assert names == {"Butter", "Yoghurt"}

    butter = next(i for i in items if i["name"] == "Butter")
    assert butter["quantity"] == "1 pack"
    assert butter["category"] == "Dairy"
    assert butter["use_by_source"] == "foodkeeper"
    assert butter["matched_name"] == "Butter, salted"
    assert butter["estimated_use_by"] == "2026-07-15T00:00:00+00:00"


@freeze_time(FROZEN_NOW)
async def test_sensor_respects_configured_window(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # A 14-day window now also catches Flour (12 days out).
    await _setup(hass, aioclient_mock, options={CONF_EXPIRY_WINDOW_DAYS: 14})

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "3"  # Butter + Yoghurt + Flour
    assert state.attributes["window_days"] == 14


@freeze_time(FROZEN_NOW)
async def test_sensor_zero_when_nothing_expiring(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(LISTS_URL, json=[])
    aioclient_mock.get(PANTRY_URL, json=[])
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u1",
        data={CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_t"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "0"
    assert state.attributes["items"] == []
