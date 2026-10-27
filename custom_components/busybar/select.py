from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import BusyBarApiError
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
    entities: list[SelectEntity] = [BusyBarBrightnessModeSelect(entry, coordinator)]
    if coordinator.data.get("apps") is not None:
        entities.append(BusyBarAppSelect(entry, coordinator))
    async_add_entities(entities)


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


class BusyBarAppSelect(CoordinatorEntity[BusyBarDataUpdateCoordinator], SelectEntity):
    """Launch an installed BUSY Bar JavaScript app.

    The API does not report which app is running, so the state is the app most
    recently launched from Home Assistant.
    """

    _attr_has_entity_name = True
    _attr_name = "Launch App"
    _attr_icon = "mdi:application-cog-outline"

    def __init__(self, entry: ConfigEntry, coordinator: BusyBarDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._entry = entry
        serial_number = coordinator.data.get("device", {}).get("serial_number", entry.entry_id)
        self._attr_unique_id = f"{serial_number}_launch_app"
        self._current: str | None = None

    def _app_ids_by_option(self) -> dict[str, str]:
        options: dict[str, str] = {}
        for app in self.coordinator.data.get("apps") or []:
            if not isinstance(app, dict) or app.get("is_debug") or not app.get("id"):
                continue
            label = app.get("name") or app["id"]
            if label in options:
                label = f"{label} ({app['id']})"
            options[label] = app["id"]
        return options

    @property
    def options(self) -> list[str]:
        return list(self._app_ids_by_option())

    @property
    def current_option(self) -> str | None:
        return self._current if self._current in self._app_ids_by_option() else None

    async def async_select_option(self, option: str) -> None:
        app_id = self._app_ids_by_option().get(option)
        if app_id is None:
            raise HomeAssistantError(f"Unknown BUSY Bar app: {option}")
        try:
            await self.coordinator.client.async_launch_app(app_id)
        except BusyBarApiError as err:
            raise HomeAssistantError(str(err)) from err
        self._current = option
        self.async_write_ha_state()

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
