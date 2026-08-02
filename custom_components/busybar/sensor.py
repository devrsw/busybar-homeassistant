from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BusyBarDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class BusyBarSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _timestamp_from_epoch(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return dt_util.utc_from_timestamp(int(value))
    except (TypeError, ValueError):
        return None


SENSORS: tuple[BusyBarSensorEntityDescription, ...] = (
    BusyBarSensorEntityDescription(
        key="battery_charge",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        suggested_display_precision=0,
        value_fn=lambda data: data.get("power", {}).get("battery_charge"),
        attributes_fn=lambda data: {
            "state": data.get("power", {}).get("state"),
            "battery_voltage_mv": data.get("power", {}).get("battery_voltage"),
            "battery_current_ma": data.get("power", {}).get("battery_current"),
            "usb_voltage_mv": data.get("power", {}).get("usb_voltage"),
        },
    ),
    BusyBarSensorEntityDescription(
        key="power_state",
        name="Power State",
        icon="mdi:battery-heart-variant",
        value_fn=lambda data: data.get("power", {}).get("state"),
    ),
    BusyBarSensorEntityDescription(
        key="battery_voltage",
        name="Battery Voltage",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="mV",
        suggested_display_precision=0,
        icon="mdi:lightning-bolt",
        value_fn=lambda data: data.get("power", {}).get("battery_voltage"),
    ),
    BusyBarSensorEntityDescription(
        key="battery_current",
        name="Battery Current",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="mA",
        suggested_display_precision=0,
        icon="mdi:current-dc",
        value_fn=lambda data: data.get("power", {}).get("battery_current"),
    ),
    BusyBarSensorEntityDescription(
        key="usb_voltage",
        name="USB Voltage",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="mV",
        suggested_display_precision=0,
        icon="mdi:usb-port",
        value_fn=lambda data: data.get("power", {}).get("usb_voltage"),
    ),
    BusyBarSensorEntityDescription(
        key="firmware_version",
        name="Firmware Version",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
        value_fn=lambda data: data.get("firmware", {}).get("version"),
        attributes_fn=lambda data: {
            "target": data.get("firmware", {}).get("target"),
            "branch": data.get("firmware", {}).get("branch"),
            "build_date": data.get("firmware", {}).get("build_date"),
            "commit_hash": data.get("firmware", {}).get("commit_hash"),
            "intercom_version": data.get("firmware", {}).get("intercom_version"),
            "nwp_version": data.get("firmware", {}).get("nwp_version"),
            "matter_version": data.get("firmware", {}).get("matter_version"),
        },
    ),
    BusyBarSensorEntityDescription(
        key="api_version",
        name="API Version",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:api",
        value_fn=lambda data: data.get("system", {}).get("api_semver"),
        attributes_fn=lambda data: {
            "boot_time": data.get("system", {}).get("boot_time"),
            "auto_update_enabled": data.get("system", {}).get("auto_update_enabled"),
        },
    ),
    BusyBarSensorEntityDescription(
        key="serial_number",
        name="Serial Number",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:identifier",
        value_fn=lambda data: data.get("device", {}).get("serial_number"),
    ),
    BusyBarSensorEntityDescription(
        key="firmware_security",
        name="Firmware Security",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:shield-check-outline",
        value_fn=lambda data: data.get("device", {}).get("firmware_security"),
    ),
    BusyBarSensorEntityDescription(
        key="boot_time",
        name="Last Boot",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: _timestamp_from_epoch(data.get("system", {}).get("boot_time")),
    ),
    BusyBarSensorEntityDescription(
        key="firmware_branch",
        name="Firmware Branch",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:source-branch",
        value_fn=lambda data: data.get("firmware", {}).get("branch"),
    ),
    BusyBarSensorEntityDescription(
        key="firmware_target",
        name="Firmware Target",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:target",
        value_fn=lambda data: data.get("firmware", {}).get("target"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BusyBarDataUpdateCoordinator = runtime_data.coordinator
    async_add_entities(BusyBarSensor(entry, coordinator, description) for description in SENSORS)


class BusyBarSensor(CoordinatorEntity[BusyBarDataUpdateCoordinator], SensorEntity):
    """Representation of a BUSY Bar sensor."""

    entity_description: BusyBarSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: BusyBarDataUpdateCoordinator,
        description: BusyBarSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry

        serial_number = coordinator.data.get("device", {}).get("serial_number", entry.entry_id)
        self._attr_unique_id = f"{serial_number}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)

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