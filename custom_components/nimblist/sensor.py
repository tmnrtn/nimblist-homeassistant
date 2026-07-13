"""Sensor platform for Nimblist — pantry items nearing their estimated use-by.

The state is a **count** of pantry items whose ``EstimatedUseBy`` falls within a
configurable window (default 7 days) of now. ``EstimatedUseBy`` is a storage-time
**estimate** derived from the embedded USDA FoodKeeper dataset — it is not
food-safety advice.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import NimblistConfigEntry
from .const import CONF_EXPIRY_WINDOW_DAYS, DEFAULT_EXPIRY_WINDOW_DAYS
from .coordinator import NimblistPantryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NimblistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the pantry "expiring soon" sensor."""
    async_add_entities(
        [NimblistPantryExpiringSensor(entry.runtime_data.pantry_coordinator, entry)]
    )


def _parse_use_by(raw: Any) -> Any:
    """Parse an ISO ``estimatedUseBy`` into a tz-aware datetime, or None."""
    if not raw:
        return None
    parsed = dt_util.parse_datetime(raw)
    if parsed is None:
        return None
    # Guard naive datetimes so the comparison below never raises.
    if parsed.tzinfo is None:
        parsed = dt_util.as_local(parsed)
    return parsed


class NimblistPantryExpiringSensor(
    CoordinatorEntity[NimblistPantryCoordinator], SensorEntity
):
    """Counts pantry items whose estimated use-by is within the configured window."""

    _attr_name = "Pantry expiring soon"
    _attr_icon = "mdi:food-off-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "items"

    def __init__(
        self, coordinator: NimblistPantryCoordinator, entry: NimblistConfigEntry
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_pantry_expiring"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def _window_days(self) -> int:
        return self._entry.options.get(
            CONF_EXPIRY_WINDOW_DAYS, DEFAULT_EXPIRY_WINDOW_DAYS
        )

    def _expiring_items(self) -> list[dict[str, Any]]:
        """Return the pantry items whose estimate falls within the window."""
        data = self.coordinator.data
        if not data:
            return []
        cutoff = dt_util.now() + timedelta(days=self._window_days)
        expiring: list[dict[str, Any]] = []
        for item in data.values():
            use_by = _parse_use_by(item.get("estimatedUseBy"))
            if use_by is not None and use_by <= cutoff:
                expiring.append(item)
        return expiring

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return len(self._expiring_items())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """List the expiring items. These are estimates, not food-safety advice."""
        items = [
            {
                "name": item.get("name"),
                "quantity": item.get("quantity"),
                "estimated_use_by": item.get("estimatedUseBy"),
                "category": item.get("categoryName"),
                "use_by_source": item.get("useBySource"),
                "matched_name": item.get("useByMatchedName"),
            }
            for item in self._expiring_items()
        ]
        return {
            "window_days": self._window_days,
            "items": items,
        }
