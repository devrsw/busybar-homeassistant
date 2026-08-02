from __future__ import annotations

import re

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BusyBarDataUpdateCoordinator

NAME_PATTERN = re.compile(r'^[a-zA-Z0-9 !()_=+;:,.?\'"|@#$%^&*\[\]{}/\\<>-]+$')


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BusyBarDataUpdateCoordinator = runtime_data.coordinator
    async_add_entities([BusyBarNameText(entry, coordinator)])


class BusyBarNameText(CoordinatorEntity[BusyBarDataUpdateCoordinator], TextEntity):
    _attr_has_entity_name = True
    _attr_name = "Device Name"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:rename-box"
    _attr_native_min = 1
    _attr_native_max = 20
    _attr_pattern = NAME_PATTERN.pattern

    def __init__(self, entry: ConfigEntry, coordinator: BusyBarDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._entry = entry
        serial_number = coordinator.data.get("device", {}).get("serial_number", entry.entry_id)
        self._attr_unique_id = f"{serial_number}_device_name"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.get("name", {}).get("name") or self._entry.title

    async def async_set_value(self, value: str) -> None:
        if not 1 <= len(value) <= 20:
            raise ValueError("Device name must be between 1 and 20 characters")
        if not NAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Device name contains unsupported characters"
            )
        await self.coordinator.client.async_set_name(value)
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        device = self.coordinator.data.get("device", {})
        firmware = self.coordinator.data.get("firmware", {})
        serial_number = device.get("serial_number", self._entry.entry_id)
        return DeviceInfo(
            identifiers={(DOMAIN, serial_number)},
            manufacturer="BUSY",
            model=device.get("otp_model", "BUSY Bar"),
            name=self.coordinator.data.get("name", {}).get("name") or self._entry.title,
            serial_number=serial_number,
            sw_version=firmware.get("version"),
        )