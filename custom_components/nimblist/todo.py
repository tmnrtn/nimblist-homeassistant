"""Todo platform for Nimblist — one entity per (non-template) shopping list."""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NimblistConfigEntry
from .api import NimblistAuthError, NimblistConnectionError, NimblistItemGoneError
from .coordinator import NimblistDataUpdateCoordinator

# Serialise write service calls so concurrent HA automations don't race each other's
# add/update/delete against the same list (#1125).
PARALLEL_UPDATES = 1

# Nimblist's Item.Quantity is [MaxLength(50)]. HA maps a to-do item's description onto it, so
# reject over-length input up front with a clear message instead of an opaque API 400 (#1125).
_MAX_QUANTITY_LEN = 50

# Nimblist's Item.Name is [MaxLength(200)]; HA maps a to-do item's summary onto it (#1282).
_MAX_SUMMARY_LEN = 200


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NimblistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the todo entities and keep them in sync with the lists."""
    coordinator = entry.runtime_data
    known: dict[str, NimblistTodoListEntity] = {}

    @callback
    def _async_sync_entities() -> None:
        current = set(coordinator.data)
        new = [
            NimblistTodoListEntity(coordinator, list_id)
            for list_id in current - set(known)
        ]
        for entity in new:
            known[entity.list_id] = entity
        if new:
            async_add_entities(new)
        # Remove entities for lists that no longer exist.
        for list_id in set(known) - current:
            entity = known.pop(list_id)
            entity.hass.async_create_task(entity.async_remove(force_remove=True))

    _async_sync_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_sync_entities))


class NimblistTodoListEntity(
    CoordinatorEntity[NimblistDataUpdateCoordinator], TodoListEntity
):
    """A Home Assistant to-do list backed by a Nimblist shopping list."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(
        self, coordinator: NimblistDataUpdateCoordinator, list_id: str
    ) -> None:
        """Initialise the entity for a given list id."""
        super().__init__(coordinator)
        self.list_id = list_id
        self._attr_unique_id = list_id

    @property
    def _list(self) -> dict[str, Any] | None:
        return self.coordinator.data.get(self.list_id)

    @property
    def available(self) -> bool:
        return super().available and self._list is not None

    @property
    def name(self) -> str | None:
        lst = self._list
        return lst["name"] if lst else None

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Map Nimblist items to Home Assistant to-do items."""
        lst = self._list
        if lst is None:
            return None
        return [
            TodoItem(
                uid=item["id"],
                summary=item["name"],
                status=(
                    TodoItemStatus.COMPLETED
                    if item.get("isChecked")
                    else TodoItemStatus.NEEDS_ACTION
                ),
                description=item.get("quantity") or None,
            )
            for item in lst["items"].values()
        ]

    def _reauth(self, err: NimblistAuthError) -> None:
        """Turn a mid-write auth failure into a reauth prompt + user-visible error (#1125)."""
        self.coordinator.config_entry.async_start_reauth(self.hass)
        raise HomeAssistantError(
            "Nimblist rejected the API token. Reconnect the integration with a new token."
        ) from err

    @staticmethod
    def _validate_description(item: TodoItem) -> None:
        """Reject an over-length description before it hits the 50-char quantity cap (#1125)."""
        if item.description and len(item.description) > _MAX_QUANTITY_LEN:
            raise HomeAssistantError(
                f"Nimblist stores the description as the item quantity, capped at "
                f"{_MAX_QUANTITY_LEN} characters."
            )

    @staticmethod
    def _validate_summary(item: TodoItem) -> None:
        """Reject an over-length name before it hits the 200-char Item.Name cap (#1282)."""
        if item.summary and len(item.summary) > _MAX_SUMMARY_LEN:
            raise HomeAssistantError(
                f"Nimblist item names are capped at {_MAX_SUMMARY_LEN} characters."
            )

    @staticmethod
    def _wrap_write(err: NimblistConnectionError) -> None:
        """Surface a connection/API failure as a clean HA error instead of a raw traceback (#1282)."""
        raise HomeAssistantError(
            "Nimblist could not be reached. Please try again shortly."
        ) from err

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add a new item to the list."""
        self._validate_summary(item)
        self._validate_description(item)
        try:
            await self.coordinator.client.async_add_item(
                self.list_id,
                item.summary or "",
                quantity=item.description or None,
                checked=item.status == TodoItemStatus.COMPLETED,
            )
        except NimblistAuthError as err:
            self._reauth(err)
        except NimblistConnectionError as err:
            self._wrap_write(err)
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update an item (rename / quantity / check-uncheck)."""
        self._validate_summary(item)
        self._validate_description(item)
        lst = self._list
        current = lst["items"].get(item.uid) if lst else None
        if current is None:
            # Concurrently removed — just resync.
            await self.coordinator.async_request_refresh()
            return

        # Merge onto the full current item so the row-replacing PUT keeps fields HA didn't edit.
        merged = dict(current)
        if item.summary is not None:
            merged["name"] = item.summary
        if item.description is not None:
            merged["quantity"] = item.description
        if item.status is not None:
            merged["isChecked"] = item.status == TodoItemStatus.COMPLETED

        try:
            await self.coordinator.client.async_update_item(merged)
        except NimblistItemGoneError:
            pass
        except NimblistAuthError as err:
            self._reauth(err)
        except NimblistConnectionError as err:
            self._wrap_write(err)
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete one or more items."""
        for uid in uids:
            try:
                await self.coordinator.client.async_delete_item(uid)
            except NimblistItemGoneError:
                pass
            except NimblistAuthError as err:
                self._reauth(err)
            except NimblistConnectionError as err:
                self._wrap_write(err)
        await self.coordinator.async_request_refresh()
