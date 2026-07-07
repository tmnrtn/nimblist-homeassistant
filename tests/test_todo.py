"""Tests for the Nimblist todo platform (setup + entity behaviour)."""

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
ENTITY_ID = "todo.groceries"


def _lists_payload() -> list[dict[str, Any]]:
    return [
        {
            "id": "l1",
            "name": "Groceries",
            "isTemplate": False,
            "items": [
                {"id": "i1", "name": "Milk", "quantity": "2", "isChecked": False,
                 "shoppingListId": "l1", "categoryId": "c1", "subCategoryId": None},
                {"id": "i2", "name": "Eggs", "quantity": None, "isChecked": True,
                 "shoppingListId": "l1", "categoryId": None, "subCategoryId": None},
            ],
        },
        {"id": "t1", "name": "Template", "isTemplate": True, "items": []},
    ]


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> MockConfigEntry:
    aioclient_mock.get(LISTS_URL, json=_lists_payload())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u1",
        data={CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_t"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_entity_excluding_template(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = await _setup(hass, aioclient_mock)

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "1"  # one incomplete item (Milk)
    # The template list did not create an entity.
    assert hass.states.get("todo.template") is None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_get_items_maps_fields(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)

    result = await hass.services.async_call(
        "todo", "get_items", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True, return_response=True
    )
    items = result[ENTITY_ID]["items"]
    by_uid = {i["uid"]: i for i in items}

    assert by_uid["i1"]["summary"] == "Milk"
    assert by_uid["i1"]["status"] == "needs_action"
    assert by_uid["i1"]["description"] == "2"  # quantity → description
    assert by_uid["i2"]["status"] == "completed"


async def test_add_item_posts_to_api(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.post(f"{BASE}/api/items", json={"id": "i3"}, status=201)

    await hass.services.async_call(
        "todo", "add_item", {ATTR_ENTITY_ID: ENTITY_ID, "item": "Bread"}, blocking=True
    )

    post = [c for c in aioclient_mock.mock_calls if c[0] == "POST"][-1]
    _, _, body, _ = post
    assert body["name"] == "Bread"
    assert body["shoppingListId"] == "l1"
    assert body["isChecked"] is False


async def test_update_item_preserves_quantity_and_category(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.put(f"{BASE}/api/items/i1", status=204)

    # Mark Milk complete (status only) — quantity "2" and category c1 must survive.
    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: ENTITY_ID, "item": "i1", "status": "completed"},
        blocking=True,
    )

    put = [c for c in aioclient_mock.mock_calls if c[0] == "PUT"][-1]
    _, _, body, _ = put
    assert body["isChecked"] is True
    assert body["quantity"] == "2"
    assert body["categoryId"] == "c1"


async def test_remove_item_deletes_via_api(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.delete(f"{BASE}/api/items/i2", status=204)

    await hass.services.async_call(
        "todo", "remove_item", {ATTR_ENTITY_ID: ENTITY_ID, "item": "i2"}, blocking=True
    )

    assert any(c[0] == "DELETE" and str(c[1]).endswith("/api/items/i2") for c in aioclient_mock.mock_calls)


async def test_list_removal_removes_entity(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = await _setup(hass, aioclient_mock)
    assert hass.states.get(ENTITY_ID) is not None

    # The next poll returns no lists → the entity should be removed.
    aioclient_mock.clear_requests()
    aioclient_mock.get(LISTS_URL, json=[])
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID) is None


async def test_update_swallows_conflict(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.put(f"{BASE}/api/items/i1", status=409)

    # A concurrent-delete 409 must not bubble up as a service error.
    await hass.services.async_call(
        "todo",
        "update_item",
        {ATTR_ENTITY_ID: ENTITY_ID, "item": "i1", "status": "completed"},
        blocking=True,
    )


async def test_delete_swallows_missing_item(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    await _setup(hass, aioclient_mock)
    # A concurrently-deleted item returns 404 → treated as an idempotent success, not an error (#1125).
    aioclient_mock.delete(f"{BASE}/api/items/i2", status=404)

    await hass.services.async_call(
        "todo", "remove_item", {ATTR_ENTITY_ID: ENTITY_ID, "item": "i2"}, blocking=True
    )


async def test_add_item_wraps_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # A non-auth/non-gone API failure (500) must surface as a clean HomeAssistantError, not a raw
    # NimblistConnectionError traceback (#1282).
    await _setup(hass, aioclient_mock)
    aioclient_mock.post(f"{BASE}/api/items", status=500)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo", "add_item", {ATTR_ENTITY_ID: ENTITY_ID, "item": "Bread"}, blocking=True
        )


async def test_add_item_rejects_overlong_name(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # Item.Name is [MaxLength(200)] on the API; reject over-length up front instead of an opaque
    # 400, and don't even hit the API (#1282).
    await _setup(hass, aioclient_mock)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "todo",
            "add_item",
            {ATTR_ENTITY_ID: ENTITY_ID, "item": "x" * 201},
            blocking=True,
        )

    assert not [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
