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


def _make_input_press(key: str):
    async def _async_press(coordinator: BusyBarDataUpdateCoordinator) -> None:
        await coordinator.client.async_send_input_key(key)
        await coordinator.async_request_refresh()

    return _async_press


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
    BusyBarButtonDescription(
        key="input_up",
        name="Input Up",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:arrow-up-circle-outline",
        press_fn=_make_input_press("up"),
    ),
    BusyBarButtonDescription(
        key="input_down",
        name="Input Down",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:arrow-down-circle-outline",
        press_fn=_make_input_press("down"),
    ),
    BusyBarButtonDescription(
        key="input_start",
        name="Input Start",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:play-pause",
        press_fn=_make_input_press("start"),
    ),
    BusyBarButtonDescription(
        key="input_busy",
        name="Input Busy",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:briefcase-clock-outline",
        press_fn=_make_input_press("busy"),
    ),
    BusyBarButtonDescription(
        key="input_custom",
        name="Input Custom",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:tune-variant",
        press_fn=_make_input_press("custom"),
    ),
    BusyBarButtonDescription(
        key="input_ok",
        name="Input OK",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:check-circle-outline",
        press_fn=_make_input_press("ok"),
    ),
    BusyBarButtonDescription(
        key="input_back",
        name="Input Back",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:arrow-left-circle-outline",
        press_fn=_make_input_press("back"),
    ),
    BusyBarButtonDescription(
        key="input_apps",
        name="Input Apps",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:apps",
        press_fn=_make_input_press("apps"),
    ),
    BusyBarButtonDescription(
        key="input_settings",
        name="Input Settings",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:cog-outline",
        press_fn=_make_input_press("settings"),
    ),
    BusyBarButtonDescription(
        key="input_off",
        name="Input Off",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:power",
        press_fn=_make_input_press("off"),
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