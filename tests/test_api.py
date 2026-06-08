"""Tests for the Nimblist API client."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nimblist.api import (
    NimblistApiClient,
    NimblistAuthError,
    NimblistConnectionError,
    NimblistItemGoneError,
)

BASE = "https://nimblist.test"
TOKEN = "nbl_test"


def _client(hass: HomeAssistant) -> NimblistApiClient:
    return NimblistApiClient(BASE, TOKEN, async_get_clientsession(hass))


async def test_validate_returns_userinfo_and_sends_api_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/api/auth/userinfo", json={"userId": "u1", "email": "a@b.c"})

    info = await _client(hass).async_validate()

    assert info["userId"] == "u1"
    _, _, _, headers = aioclient_mock.mock_calls[-1]
    assert headers["X-Api-Key"] == TOKEN


async def test_validate_raises_auth_error_on_401(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/api/auth/userinfo", status=401)
    with pytest.raises(NimblistAuthError):
        await _client(hass).async_validate()


async def test_get_lists_returns_payload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    lists = [{"id": "l1", "name": "Groceries", "isTemplate": False, "items": []}]
    aioclient_mock.get(f"{BASE}/api/shoppinglists", json=lists)

    assert await _client(hass).async_get_lists() == lists


async def test_add_item_posts_expected_body(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/api/items", json={"id": "i1"}, status=201)

    await _client(hass).async_add_item("l1", "Milk", quantity="2", checked=False)

    _, _, body, _ = aioclient_mock.mock_calls[-1]
    assert body == {"name": "Milk", "quantity": "2", "isChecked": False, "shoppingListId": "l1"}


async def test_update_item_preserves_quantity_and_category(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.put(f"{BASE}/api/items/i1", status=204)

    # Full current item with only isChecked flipped — quantity/category must survive.
    item = {
        "id": "i1",
        "name": "Milk",
        "quantity": "2",
        "isChecked": True,
        "shoppingListId": "l1",
        "categoryId": "c1",
        "subCategoryId": "s1",
    }
    await _client(hass).async_update_item(item)

    _, _, body, _ = aioclient_mock.mock_calls[-1]
    assert body["isChecked"] is True
    assert body["quantity"] == "2"
    assert body["categoryId"] == "c1"
    assert body["subCategoryId"] == "s1"
    assert body["shoppingListId"] == "l1"


async def test_update_item_raises_gone_on_409(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.put(f"{BASE}/api/items/i1", status=409)
    item = {"id": "i1", "name": "Milk", "isChecked": True, "shoppingListId": "l1"}
    with pytest.raises(NimblistItemGoneError):
        await _client(hass).async_update_item(item)


async def test_delete_item_succeeds_on_204(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.delete(f"{BASE}/api/items/i1", status=204)
    await _client(hass).async_delete_item("i1")  # no exception


async def test_connection_error_wraps_transport_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/api/shoppinglists", exc=aiohttp.ClientError())
    with pytest.raises(NimblistConnectionError):
        await _client(hass).async_get_lists()


async def test_unexpected_status_raises_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/api/shoppinglists", status=500)
    with pytest.raises(NimblistConnectionError):
        await _client(hass).async_get_lists()
