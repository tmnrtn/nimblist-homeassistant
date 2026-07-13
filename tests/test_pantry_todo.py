"""Tests for the Nimblist pantry stock (todo) entity."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nimblist.const import CONF_API_TOKEN, CONF_BASE_URL, DOMAIN

BASE = "https://nimblist.test"
LISTS_URL = f"{BASE}/api/shoppinglists"
PANTRY_URL = f"{BASE}/api/pantry"
ENTITY_ID = "todo.pantry"


def _pantry_payload() -> list[dict[str, Any]]:
    return [
        {
            "id": "p1",
            "name": "Butter",
            "quantity": "1 pack",
            "categoryName": "Dairy",
            "estimatedUseBy": "2026-08-01T00:00:00Z",
            "useBySource": "foodkeeper",
            "useByMatchedName": "Butter, salted",
        },
        {
            "id": "p2",
            "name": "Flour",
            "quantity": None,
            "categoryName": "Baking",
            "estimatedUseBy": None,
            "useBySource": None,
            "useByMatchedName": None,
        },
    ]


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> MockConfigEntry:
    aioclient_mock.get(LISTS_URL, json=[])
    aioclient_mock.get(PANTRY_URL, json=_pantry_payload())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u1",
        data={CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_t"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_pantry_entity(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = await _setup(hass, aioclient_mock)

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    # Pantry is stock, not a checklist → count is the total number of items.
    assert state.state == "2"


async def test_get_items_maps_fields(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)

    result = await hass.services.async_call(
        "todo", "get_items", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True, return_response=True
    )
    items = result[ENTITY_ID]["items"]
    by_uid = {i["uid"]: i for i in items}

    assert by_uid["p1"]["summary"] == "Butter"
    assert by_uid["p1"]["description"] == "1 pack"  # quantity → description
    assert by_uid["p1"]["status"] == "needs_action"  # stock, never completed
    assert by_uid["p1"]["due"] == "2026-08-01"  # estimatedUseBy → due date
    # No estimate → no due date, no description.
    assert by_uid["p2"]["summary"] == "Flour"
    assert "due" not in by_uid["p2"] or by_uid["p2"].get("due") is None
    assert by_uid["p2"].get("description") in (None, "")


async def test_add_item_posts_name_and_quantity_only(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.post(PANTRY_URL, json={"id": "p3"}, status=201)

    await hass.services.async_call(
        "todo",
        "add_item",
        {ATTR_ENTITY_ID: ENTITY_ID, "item": "Eggs"},
        blocking=True,
    )

    post = [c for c in aioclient_mock.mock_calls if c[0] == "POST"][-1]
    _, _, body, _ = post
    assert body == {"name": "Eggs", "quantity": None}


async def test_update_item_sends_only_name_and_quantity(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.put(f"{PANTRY_URL}/p1", status=204)

    # Rename via a new quantity — the PUT must carry only name + quantity, no category.
    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: ENTITY_ID, "item": "p1", "rename": "Butter", "description": "2 packs"},
        blocking=True,
    )

    put = [c for c in aioclient_mock.mock_calls if c[0] == "PUT"][-1]
    _, _, body, _ = put
    assert body == {"name": "Butter", "quantity": "2 packs"}


async def test_remove_item_deletes_via_api(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.delete(f"{PANTRY_URL}/p2", status=204)

    await hass.services.async_call(
        "todo", "remove_item", {ATTR_ENTITY_ID: ENTITY_ID, "item": "Flour"}, blocking=True
    )

    assert any(
        c[0] == "DELETE" and str(c[1]).endswith("/api/pantry/p2")
        for c in aioclient_mock.mock_calls
    )


async def test_update_swallows_conflict(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.put(f"{PANTRY_URL}/p1", status=409)

    # A concurrent-modify 409 must not bubble up as a service error.
    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: ENTITY_ID, "item": "p1", "description": "3 packs"},
        blocking=True,
    )


async def test_delete_swallows_missing_item(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.delete(f"{PANTRY_URL}/p2", status=404)

    await hass.services.async_call(
        "todo", "remove_item", {ATTR_ENTITY_ID: ENTITY_ID, "item": "Flour"}, blocking=True
    )


async def test_add_item_wraps_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.post(PANTRY_URL, status=500)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo", "add_item", {ATTR_ENTITY_ID: ENTITY_ID, "item": "Eggs"}, blocking=True
        )


async def test_add_item_rejects_overlong_name(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo",
            "add_item",
            {ATTR_ENTITY_ID: ENTITY_ID, "item": "x" * 201},
            blocking=True,
        )

    assert not [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
