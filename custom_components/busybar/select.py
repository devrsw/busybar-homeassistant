from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BusyBarDataUpdateCoordinator


def _brightness_to_int(value: Any) -> int | None:
    if isinstance(value, str) and value.isdigit():
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BusyBarDataUpdateCoordinator = runtime_data.coordinator
    async_add_entities([BusyBarBrightnessModeSelect(entry, coordinator)])


class BusyBarBrightnessModeSelect(CoordinatorEntity[BusyBarDataUpdateCoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Brightness Mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:theme-light-dark"
    _attr_options = ["auto", "manual"]

    def __init__(self, entry: ConfigEntry, coordinator: BusyBarDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._entry = entry
        serial_number = coordinator.data.get("device", {}).get("serial_number", entry.entry_id)
        self._attr_unique_id = f"{serial_number}_brightness_mode"
        self._last_manual_value = _brightness_to_int(
            coordinator.data.get("display", {}).get("brightness")
        ) or 50

    @property
    def current_option(self) -> str | None:
        brightness = self.coordinator.data.get("display", {}).get("brightness")
        value = _brightness_to_int(brightness)
        if value is not None:
            self._last_manual_value = value
            return "manual"
        if brightness == "auto":
            return "auto"
        return None

    async def async_select_option(self, option: str) -> None:
        if option == "auto":
            await self.coordinator.client.async_set_brightness("auto")
        else:
            await self.coordinator.client.async_set_brightness(str(self._last_manual_value))
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
            name=self._entry.title,
            serial_number=serial_number,
            sw_version=firmware.get("version"),
        )