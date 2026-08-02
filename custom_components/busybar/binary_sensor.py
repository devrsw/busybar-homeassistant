from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BusyBarDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class BusyBarBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[BusyBarBinarySensorDescription, ...] = (
    BusyBarBinarySensorDescription(
        key="auto_update_enabled",
        name="Auto Update Enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:update-auto",
        value_fn=lambda data: data.get("system", {}).get("auto_update_enabled"),
    ),
    BusyBarBinarySensorDescription(
        key="busy_timer_paused",
        name="Busy Timer Paused",
        icon="mdi:pause-circle-outline",
        value_fn=lambda data: data.get("busy", {}).get("snapshot", {}).get("is_paused"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BusyBarDataUpdateCoordinator = runtime_data.coordinator
    async_add_entities(
        BusyBarBinarySensor(entry, coordinator, description)
        for description in BINARY_SENSORS
    )


class BusyBarBinarySensor(
    CoordinatorEntity[BusyBarDataUpdateCoordinator], BinarySensorEntity
):
    entity_description: BusyBarBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BusyBarDataUpdateCoordinator,
        description: BusyBarBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry

        serial_number = coordinator.data.get("device", {}).get("serial_number", entry.entry_id)
        self._attr_unique_id = f"{serial_number}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def device_info(self) -> DeviceInfo:
        device = self.coordinator.data.get("device", {})
        firmware = self.coordinator.data.get("firmware", {})
        serial_number = device.get("serial_number", self._entry.entry_id)
        return DeviceInfo(
            identifiers={(DOMAIN, serial_number)},
            manufacturer="BUSY",
            model=device.get("otp_model", "BUSY Bar"),
            name=self._entry.title,
            serial_number=serial_number,
            sw_version=firmware.get("version"),
        )