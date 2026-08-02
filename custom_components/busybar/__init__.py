from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_TOKEN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import BusyBarApiClient
from .const import (
    ATTR_APPLICATION_NAME,
    ATTR_DURATION,
    ATTR_ENTRY_ID,
    ATTR_LED_NOTIFICATION_COLOR,
    ATTR_PAYLOAD,
    CONF_BASE_URL,
    CONF_POLL_INTERVAL,
    DATA_SERVICES_REGISTERED,
    DEFAULT_APPLICATION_NAME,
    DEFAULT_DRAW_PRIORITY,
    DISPLAY_ALIGNMENTS,
    DISPLAY_FONTS,
    DISPLAY_FRONT,
    DISPLAY_NAMES,
    DOMAIN,
    MAX_BRIGHTNESS,
    MAX_VOLUME,
    SERVICE_CLEAR_DISPLAY,
    SERVICE_DRAW_DASHBOARD,
    SERVICE_DRAW_TEXT,
    SERVICE_SET_BRIGHTNESS,
    SERVICE_SET_VOLUME,
)
from .coordinator import BusyBarDataUpdateCoordinator

LOGGER = logging.getLogger(__name__)
PLATFORMS = ["binary_sensor", "button", "number", "select", "sensor", "text"]
COLOR_HEX_PATTERN = vol.Match(r"^#[A-Fa-f0-9]{8}$")


@dataclass
class BusyBarRuntimeData:
    """Runtime objects for a BUSY Bar entry."""

    client: BusyBarApiClient
    coordinator: BusyBarDataUpdateCoordinator


def _validate_ascii_text(value: str) -> str:
    if not value:
        raise vol.Invalid("Text must not be empty")
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise vol.Invalid("BUSY Bar text must contain printable ASCII characters only")
    return value


def _validate_dashboard_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ServiceValidationError("Dashboard payload must be an object")

    normalized = dict(payload)
    normalized.setdefault(ATTR_APPLICATION_NAME, DEFAULT_APPLICATION_NAME)
    normalized.setdefault("priority", DEFAULT_DRAW_PRIORITY)

    elements = normalized.get("elements")
    if not isinstance(elements, list) or not elements:
        raise ServiceValidationError("Dashboard payload must include a non-empty elements list")

    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            raise ServiceValidationError(
                f"Dashboard element at index {index} must be an object"
            )
        if element.get("type") == "text":
            text = element.get("text")
            if not isinstance(text, str):
                raise ServiceValidationError(
                    f"Dashboard text element at index {index} must include text"
                )
            _validate_ascii_text(text)

    return normalized


DRAW_TEXT_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_APPLICATION_NAME, default=DEFAULT_APPLICATION_NAME): cv.string,
        vol.Required("text"): vol.All(cv.string, _validate_ascii_text),
        vol.Optional("display", default=DISPLAY_FRONT): vol.In(DISPLAY_NAMES),
        vol.Optional("font", default="normal"): vol.In(DISPLAY_FONTS),
        vol.Optional("align", default="center"): vol.In(DISPLAY_ALIGNMENTS),
        vol.Optional("color", default="#FFFFFFFF"): COLOR_HEX_PATTERN,
        vol.Optional(ATTR_LED_NOTIFICATION_COLOR): COLOR_HEX_PATTERN,
        vol.Optional("priority", default=DEFAULT_DRAW_PRIORITY): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional("x", default=0): vol.Coerce(int),
        vol.Optional("y", default=0): vol.Coerce(int),
        vol.Optional("width"): vol.All(vol.Coerce(int), vol.Range(min=1, max=160)),
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
        vol.Optional("clear_before_draw", default=False): cv.boolean,
    }
)

DRAW_DASHBOARD_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_PAYLOAD): dict,
        vol.Optional("clear_before_draw", default=False): cv.boolean,
    }
)

CLEAR_DISPLAY_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_APPLICATION_NAME): cv.string,
    }
)

SET_BRIGHTNESS_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required("value"): vol.Any(
            "auto", vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_BRIGHTNESS))
        ),
    }
)

SET_VOLUME_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required("volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_VOLUME)),
        vol.Optional("silent", default=True): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the BUSY Bar integration."""

    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BUSY Bar from a config entry."""

    session = async_get_clientsession(hass)
    client = BusyBarApiClient(
        session,
        entry.data[CONF_BASE_URL],
        entry.data.get(CONF_TOKEN),
    )
    coordinator = BusyBarDataUpdateCoordinator(
        hass,
        client=client,
        config_entry=entry,
        update_interval=timedelta(seconds=entry.data[CONF_POLL_INTERVAL]),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = BusyBarRuntimeData(
        client=client,
        coordinator=coordinator,
    )

    await _async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a BUSY Bar config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    domain_data = hass.data[DOMAIN]
    domain_data.pop(entry.entry_id, None)

    remaining_entries = [key for key in domain_data if key != DATA_SERVICES_REGISTERED]
    if not remaining_entries:
        for service_name in (
            SERVICE_DRAW_TEXT,
            SERVICE_DRAW_DASHBOARD,
            SERVICE_CLEAR_DISPLAY,
            SERVICE_SET_BRIGHTNESS,
            SERVICE_SET_VOLUME,
        ):
            hass.services.async_remove(DOMAIN, service_name)
        domain_data.pop(DATA_SERVICES_REGISTERED, None)

    return True


def _get_runtime_data(hass: HomeAssistant, entry_id: str | None) -> BusyBarRuntimeData:
    domain_data = hass.data.get(DOMAIN, {})
    available_entry_ids = [key for key in domain_data if key != DATA_SERVICES_REGISTERED]
    if not available_entry_ids:
        raise ServiceValidationError("No BUSY Bar entries are configured")

    if entry_id:
        runtime_data = domain_data.get(entry_id)
        if runtime_data is None:
            raise ServiceValidationError(f"Unknown BUSY Bar entry_id: {entry_id}")
        return runtime_data

    if len(available_entry_ids) > 1:
        raise ServiceValidationError(
            "More than one BUSY Bar is configured; include entry_id in the service call"
        )

    return domain_data[available_entry_ids[0]]


async def _async_register_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_SERVICES_REGISTERED):
        return

    async def async_draw_text(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))

        element: dict[str, Any] = {
            "id": "message",
            "type": "text",
            "text": call.data["text"],
            "font": call.data["font"],
            "color": call.data["color"],
            "display": call.data["display"],
            "align": call.data["align"],
            "x": call.data["x"],
            "y": call.data["y"],
        }
        if "width" in call.data:
            element["width"] = call.data["width"]
        if ATTR_DURATION in call.data:
            element["timeout"] = call.data[ATTR_DURATION]

        payload: dict[str, Any] = {
            ATTR_APPLICATION_NAME: call.data[ATTR_APPLICATION_NAME],
            "priority": call.data["priority"],
            "elements": [element],
        }
        if ATTR_LED_NOTIFICATION_COLOR in call.data:
            payload[ATTR_LED_NOTIFICATION_COLOR] = call.data[ATTR_LED_NOTIFICATION_COLOR]

        if call.data["clear_before_draw"]:
            await runtime_data.client.async_clear(call.data[ATTR_APPLICATION_NAME])
        await runtime_data.client.async_draw(payload)
        await runtime_data.coordinator.async_request_refresh()

    async def async_draw_dashboard(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        payload = _validate_dashboard_payload(call.data[ATTR_PAYLOAD])

        if call.data["clear_before_draw"]:
            await runtime_data.client.async_clear(payload[ATTR_APPLICATION_NAME])
        await runtime_data.client.async_draw(payload)
        await runtime_data.coordinator.async_request_refresh()

    async def async_clear_display(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        await runtime_data.client.async_clear(call.data.get(ATTR_APPLICATION_NAME))
        await runtime_data.coordinator.async_request_refresh()

    async def async_set_brightness(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        value = call.data["value"]
        await runtime_data.client.async_set_brightness(str(value))

    async def async_set_volume(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        await runtime_data.client.async_set_volume(call.data["volume"], call.data["silent"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_DRAW_TEXT,
        async_draw_text,
        schema=DRAW_TEXT_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DRAW_DASHBOARD,
        async_draw_dashboard,
        schema=DRAW_DASHBOARD_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_DISPLAY,
        async_clear_display,
        schema=CLEAR_DISPLAY_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BRIGHTNESS,
        async_set_brightness,
        schema=SET_BRIGHTNESS_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_VOLUME,
        async_set_volume,
        schema=SET_VOLUME_SERVICE_SCHEMA,
    )

    domain_data[DATA_SERVICES_REGISTERED] = True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: Any,
) -> bool:
    """Allow removing the device from the device registry."""

    return True