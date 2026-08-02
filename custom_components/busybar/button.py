from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_APPLICATION_NAME, DOMAIN
from .coordinator import BusyBarDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class BusyBarButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[BusyBarDataUpdateCoordinator], Awaitable[None]]


async def _async_clear_display(coordinator: BusyBarDataUpdateCoordinator) -> None:
    await coordinator.client.async_clear(DEFAULT_APPLICATION_NAME)
    await coordinator.async_request_refresh()


async def _async_stop_audio(coordinator: BusyBarDataUpdateCoordinator) -> None:
    await coordinator.client.async_stop_audio()
    await coordinator.async_request_refresh()


BUTTONS: tuple[BusyBarButtonDescription, ...] = (
    BusyBarButtonDescription(
        key="clear_display",
        name="Clear Home Assistant Display",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:monitor-clean",
        press_fn=_async_clear_display,
    ),
    BusyBarButtonDescription(
        key="stop_audio",
        name="Stop Audio",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:stop-circle-outline",
        press_fn=_async_stop_audio,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BusyBarDataUpdateCoordinator = runtime_data.coordinator
    async_add_entities(BusyBarButton(entry, coordinator, description) for description in BUTTONS)


class BusyBarButton(CoordinatorEntity[BusyBarDataUpdateCoordinator], ButtonEntity):
    entity_description: BusyBarButtonDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BusyBarDataUpdateCoordinator,
        description: BusyBarButtonDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        serial_number = coordinator.data.get("device", {}).get("serial_number", entry.entry_id)
        self._attr_unique_id = f"{serial_number}_{description.key}"

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)

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