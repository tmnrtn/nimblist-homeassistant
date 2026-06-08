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
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NimblistConfigEntry
from .api import NimblistItemGoneError
from .coordinator import NimblistDataUpdateCoordinator


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

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add a new item to the list."""
        await self.coordinator.client.async_add_item(
            self.list_id,
            item.summary or "",
            quantity=item.description or None,
            checked=item.status == TodoItemStatus.COMPLETED,
        )
        await self.coordinator.async_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update an item (rename / quantity / check-uncheck)."""
        lst = self._list
        current = lst["items"].get(item.uid) if lst else None
        if current is None:
            # Concurrently removed — just resync.
            await self.coordinator.async_refresh()
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
        await self.coordinator.async_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete one or more items."""
        for uid in uids:
            try:
                await self.coordinator.client.async_delete_item(uid)
            except NimblistItemGoneError:
                pass
        await self.coordinator.async_refresh()
