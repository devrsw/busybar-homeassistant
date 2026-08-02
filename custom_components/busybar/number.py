from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
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
    async_add_entities(
        [
            BusyBarBrightnessNumber(entry, coordinator),
            BusyBarVolumeNumber(entry, coordinator),
        ]
    )


class BusyBarBrightnessNumber(CoordinatorEntity[BusyBarDataUpdateCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Display Brightness"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:brightness-6"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = "slider"

    def __init__(self, entry: ConfigEntry, coordinator: BusyBarDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._entry = entry
        serial_number = coordinator.data.get("device", {}).get("serial_number", entry.entry_id)
        self._attr_unique_id = f"{serial_number}_display_brightness"
        self._last_manual_value = _brightness_to_int(
            coordinator.data.get("display", {}).get("brightness")
        ) or 50

    @property
    def native_value(self) -> float | None:
        value = _brightness_to_int(self.coordinator.data.get("display", {}).get("brightness"))
        if value is not None:
            self._last_manual_value = value
            return float(value)
        return float(self._last_manual_value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        brightness = self.coordinator.data.get("display", {}).get("brightness")
        return {"mode": "auto" if brightness == "auto" else "manual"}

    async def async_set_native_value(self, value: float) -> None:
        new_value = int(round(value))
        self._last_manual_value = new_value
        await self.coordinator.client.async_set_brightness(str(new_value))
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


class BusyBarVolumeNumber(CoordinatorEntity[BusyBarDataUpdateCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Audio Volume"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_mode = "slider"

    def __init__(self, entry: ConfigEntry, coordinator: BusyBarDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._entry = entry
        serial_number = coordinator.data.get("device", {}).get("serial_number", entry.entry_id)
        self._attr_unique_id = f"{serial_number}_audio_volume"

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.data.get("audio", {}).get("volume")
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        stepped = int(round(value / 5.0) * 5)
        stepped = max(0, min(100, stepped))
        await self.coordinator.client.async_set_volume(stepped, True)
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