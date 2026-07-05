"""Async API client for the Nimblist service.

Talks to the Nimblist REST API using a personal access token (the ``X-Api-Key``
header). All methods raise the typed errors below so the config flow and the
coordinator can react (reauth on auth failure, retry/refresh on transport or
concurrent-delete).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import API_KEY_HEADER

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class NimblistError(Exception):
    """Base error for the Nimblist client."""


class NimblistAuthError(NimblistError):
    """The API token was rejected (HTTP 401/403)."""


class NimblistConnectionError(NimblistError):
    """A transport-level / timeout / unexpected-status error."""


class NimblistItemGoneError(NimblistError):
    """An item was concurrently modified or deleted (HTTP 409) — refresh and retry."""


class NimblistApiClient:
    """Thin async wrapper over the Nimblist REST API."""

    def __init__(self, base_url: str, api_token: str, session: aiohttp.ClientSession) -> None:
        """Initialise the client.

        ``base_url`` is the server root (e.g. ``https://nimblist.app``); ``api_token``
        is a Nimblist personal access token (``nbl_…``).
        """
        self._base = base_url.rstrip("/")
        self._session = session
        self._headers = {API_KEY_HEADER: api_token, "Accept": "application/json"}

    async def _request(
        self, method: str, path: str, *, json: Any | None = None
    ) -> Any | None:
        """Perform a request, mapping HTTP/transport failures to typed errors."""
        url = f"{self._base}{path}"
        try:
            async with self._session.request(
                method, url, headers=self._headers, json=json, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise NimblistAuthError(f"Authentication failed ({resp.status}) for {method} {path}")
                # A write to a now-missing item is "gone", not a transport failure: the API returns
                # 409 on a concurrent-modify and 404 on a concurrent-delete (ItemsController.DeleteItem
                # / PutItem NotFound). Both mean the desired end-state is already reached, so the
                # write handlers can treat them as an idempotent no-op (#1125). 404 is only "gone" for
                # writes — on a GET it usually means a wrong base URL, which must surface as a failure.
                if resp.status == 409 or (resp.status == 404 and method in ("PUT", "DELETE")):
                    raise NimblistItemGoneError(f"Item gone/conflicted ({resp.status}) for {method} {path}")
                if resp.status >= 400:
                    body = await resp.text()
                    raise NimblistConnectionError(
                        f"Unexpected status {resp.status} for {method} {path}: {body[:200]}"
                    )
                if resp.status == 204:
                    return None
                return await resp.json()
        except NimblistError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise NimblistConnectionError(f"Connection error for {method} {path}: {err}") from err

    async def async_validate(self) -> dict[str, Any]:
        """Confirm the token works and return the authenticated user's info.

        Returns the ``/api/auth/userinfo`` payload (``userId``, ``email``, …) — used
        by the config flow for a stable unique id.
        """
        return await self._request("GET", "/api/auth/userinfo")

    async def async_get_lists(self) -> list[dict[str, Any]]:
        """Return every shopping list (each with its ``items``)."""
        return await self._request("GET", "/api/shoppinglists") or []

    async def async_add_item(
        self, list_id: str, name: str, *, quantity: str | None = None, checked: bool = False
    ) -> dict[str, Any] | None:
        """Add an item to a list."""
        body = {
            "name": name,
            "quantity": quantity,
            "isChecked": checked,
            "shoppingListId": list_id,
        }
        return await self._request("POST", "/api/items", json=body)

    async def async_update_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """Update an item.

        ``item`` must be the **full current item** (as returned by ``async_get_lists``)
        with the changed field(s) applied — the API's PUT replaces the row, so passing
        the whole object preserves ``quantity``/category that Home Assistant doesn't edit.
        """
        item_id = item["id"]
        body = {
            "name": item["name"],
            "quantity": item.get("quantity"),
            "isChecked": item["isChecked"],
            "shoppingListId": item["shoppingListId"],
            "categoryId": item.get("categoryId"),
            "subCategoryId": item.get("subCategoryId"),
        }
        return await self._request("PUT", f"/api/items/{item_id}", json=body)

    async def async_delete_item(self, item_id: str) -> None:
        """Delete an item.

        Raises :class:`NimblistItemGoneError` if the item is already gone (HTTP 404/409);
        callers treat that as an idempotent success.
        """
        await self._request("DELETE", f"/api/items/{item_id}")
