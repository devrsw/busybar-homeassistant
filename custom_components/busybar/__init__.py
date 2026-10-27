from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import timedelta
import logging
from pathlib import Path
import re
from typing import Any, TypeVar

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_TOKEN
from homeassistant.helpers.typing import StateType
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import BusyBarApiClient, BusyBarApiError
from .const import (
    APP_ID_PATTERN,
    ATTR_APP_ID,
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
    DISPLAY_BACK,
    DISPLAY_ALIGNMENTS,
    DISPLAY_FONTS,
    DISPLAY_FRONT,
    DISPLAY_NAMES,
    DOMAIN,
    EVENT_BUTTON,
    INPUT_KEYS,
    MAX_BRIGHTNESS,
    MAX_VOLUME,
    SERVICE_BIND_BUTTON_ACTION,
    SERVICE_CLEAR_BUTTON_ACTIONS,
    SERVICE_CLEAR_DISPLAY,
    SERVICE_DELETE_APP,
    SERVICE_DISABLE_LIVE_DASHBOARD,
    SERVICE_DRAW_DASHBOARD,
    SERVICE_DRAW_ENTITY_DASHBOARD,
    SERVICE_DRAW_PROGRESS_CARD,
    SERVICE_ENABLE_LIVE_ENTITY_DASHBOARD,
    SERVICE_DRAW_TEXT,
    SERVICE_DRAW_ROOM_CLIMATE_DASHBOARD,
    SERVICE_DRAW_WEATHER_DASHBOARD,
    SERVICE_GET_APP_SETTINGS,
    SERVICE_INSTALL_APP,
    SERVICE_LAUNCH_APP,
    SERVICE_QUIT_APP,
    SERVICE_RESET_APP_SETTINGS,
    SERVICE_SEND_INPUT_COMMAND,
    SERVICE_SET_APP_SETTINGS,
    SERVICE_SET_BRIGHTNESS,
    SERVICE_SET_VOLUME,
)
from .coordinator import BusyBarDataUpdateCoordinator
from .runtime import ButtonActionRegistry, ButtonEventListener, LiveDashboardController

LOGGER = logging.getLogger(__name__)
PLATFORMS = ["binary_sensor", "button", "number", "select", "sensor", "text"]
COLOR_HEX_PATTERN = vol.Match(r"^#[A-Fa-f0-9]{8}$")
APP_ID = vol.All(cv.string, vol.Match(APP_ID_PATTERN))
MAX_APP_PACKAGE_BYTES = 16 * 1024 * 1024
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass
class BusyBarRuntimeData:
    """Runtime objects for a BUSY Bar entry."""

    client: BusyBarApiClient
    coordinator: BusyBarDataUpdateCoordinator
    live_dashboard: LiveDashboardController
    button_actions: ButtonActionRegistry
    button_listener: ButtonEventListener


def _validate_ascii_text(value: str) -> str:
    if not value:
        raise vol.Invalid("Text must not be empty")
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise vol.Invalid("BUSY Bar text must contain printable ASCII characters only")
    return value


def _validate_step_5(value: int) -> int:
    if value % 5 != 0:
        raise vol.Invalid("Value must be in 5% increments")
    return value


def _coerce_ascii_text(value: Any, default: str = "") -> str:
    text = str(value or default)
    text = text.encode("ascii", "ignore").decode().strip()
    text = WHITESPACE_PATTERN.sub(" ", text)
    return text


def _get_state(hass: HomeAssistant, entity_id: str):
    state = hass.states.get(entity_id)
    if state is None:
        raise ServiceValidationError(f"Unknown entity_id: {entity_id}")
    return state


def _format_state_value(value: StateType, unit: str | None = None) -> str:
    text = _coerce_ascii_text(value)
    if unit and text not in {"", "unknown", "unavailable", "none"}:
        return _validate_ascii_text(f"{text} {unit}")
    return _validate_ascii_text(text or "unknown")


def _format_entity_line(hass: HomeAssistant, item: dict[str, Any]) -> str:
    state = _get_state(hass, item["entity_id"])

    if item.get("attribute"):
        raw_value = state.attributes.get(item["attribute"])
        if raw_value is None:
            raise ServiceValidationError(
                f"Entity {item['entity_id']} has no attribute {item['attribute']}"
            )
        value_text = _coerce_ascii_text(raw_value)
    else:
        value_text = _coerce_ascii_text(state.state)
        unit = _coerce_ascii_text(state.attributes.get("unit_of_measurement"))
        if unit and value_text not in {"unknown", "unavailable"}:
            value_text = f"{value_text} {unit}"

    label = item.get("label") or state.name or item["entity_id"].split(".", 1)[-1]
    label_text = _coerce_ascii_text(label).upper()
    line = f"{label_text}: {value_text}" if value_text else label_text
    return _validate_ascii_text(line[:72])


def _base_payload(call_data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        ATTR_APPLICATION_NAME: call_data[ATTR_APPLICATION_NAME],
        "priority": call_data["priority"],
        "elements": [],
    }
    if ATTR_LED_NOTIFICATION_COLOR in call_data:
        payload[ATTR_LED_NOTIFICATION_COLOR] = call_data[ATTR_LED_NOTIFICATION_COLOR]
    return payload


def _apply_timeout(call_data: dict[str, Any], element: dict[str, Any]) -> dict[str, Any]:
    if ATTR_DURATION in call_data:
        element["timeout"] = call_data[ATTR_DURATION]
    return element


def _build_entity_dashboard_payload(
    hass: HomeAssistant,
    call_data: dict[str, Any],
) -> dict[str, Any]:
    display = call_data["display"]
    title = _validate_ascii_text(_coerce_ascii_text(call_data["title"]).upper())
    entity_items = call_data["entities"]
    lines = [_format_entity_line(hass, item) for item in entity_items]

    payload: dict[str, Any] = {
        **_base_payload(call_data),
    }

    if display == DISPLAY_BACK:
        title_width = 152
        payload["elements"].append(
            {
                "id": "title",
                "type": "text",
                "text": title,
                "font": "bold",
                "color": call_data["title_color"],
                "display": DISPLAY_BACK,
                "align": "top_left",
                "x": 4,
                "y": 4,
                "width": title_width,
            }
        )
        for index, line in enumerate(lines[:4]):
            element = _apply_timeout(call_data, {
                "id": f"line_{index}",
                "type": "text",
                "text": line,
                "font": "normal",
                "color": call_data["color"],
                "display": DISPLAY_BACK,
                "align": "top_left",
                "x": 4,
                "y": 22 + index * 14,
                "width": 152,
                "scroll_rate": 900,
                "scroll_start_delay": 1000,
                "scroll_repeat_delay": 1800,
            })
            payload["elements"].append(element)
        return payload

    payload["elements"].append(
        {
            "id": "title",
            "type": "text",
            "text": title[:14],
            "font": "small",
            "color": call_data["title_color"],
            "display": DISPLAY_FRONT,
            "align": "top_mid",
            "x": 0,
            "y": 0,
            "width": 72,
        }
    )
    for index, line in enumerate(lines[:2]):
        element = _apply_timeout(call_data, {
            "id": f"line_{index}",
            "type": "text",
            "text": line,
            "font": "tiny",
            "color": call_data["color"],
            "display": DISPLAY_FRONT,
            "align": "top_left",
            "x": 0,
            "y": 8 + index * 6,
            "width": 72,
            "scroll_rate": 1100,
            "scroll_start_delay": 1000,
            "scroll_repeat_delay": 1600,
        })
        payload["elements"].append(element)
    return payload


def _build_weather_dashboard_payload(hass: HomeAssistant, call_data: dict[str, Any]) -> dict[str, Any]:
    display = call_data["display"]
    state = _get_state(hass, call_data["weather_entity_id"])
    condition = _validate_ascii_text(_coerce_ascii_text(state.state, "unknown").upper())
    temperature = state.attributes.get("temperature")
    temperature_unit = _coerce_ascii_text(state.attributes.get("temperature_unit"))
    humidity = state.attributes.get("humidity")
    if temperature is None:
        raise ServiceValidationError(
            f"Weather entity {call_data['weather_entity_id']} has no temperature attribute"
        )

    temp_text = _format_state_value(temperature, temperature_unit)
    humid_text = _format_state_value(humidity, "%") if humidity is not None else ""
    payload = _base_payload(call_data)

    if display == DISPLAY_BACK:
        payload["elements"].extend(
            [
                {
                    "id": "title",
                    "type": "text",
                    "text": _validate_ascii_text(_coerce_ascii_text(call_data["title"]).upper()),
                    "font": "bold",
                    "color": call_data["title_color"],
                    "display": DISPLAY_BACK,
                    "align": "top_left",
                    "x": 4,
                    "y": 4,
                    "width": 152,
                },
                _apply_timeout(call_data, {
                    "id": "condition",
                    "type": "text",
                    "text": f"NOW: {condition}"[:72],
                    "font": "normal",
                    "color": call_data["color"],
                    "display": DISPLAY_BACK,
                    "align": "top_left",
                    "x": 4,
                    "y": 24,
                    "width": 152,
                }),
                _apply_timeout(call_data, {
                    "id": "temp",
                    "type": "text",
                    "text": f"TEMP: {temp_text}"[:72],
                    "font": "large",
                    "color": call_data["accent_color"],
                    "display": DISPLAY_BACK,
                    "align": "top_left",
                    "x": 4,
                    "y": 40,
                    "width": 152,
                }),
            ]
        )
        if humid_text:
            payload["elements"].append(
                _apply_timeout(call_data, {
                    "id": "humidity",
                    "type": "text",
                    "text": f"HUMID: {humid_text}"[:72],
                    "font": "normal",
                    "color": call_data["color"],
                    "display": DISPLAY_BACK,
                    "align": "top_left",
                    "x": 4,
                    "y": 62,
                    "width": 152,
                })
            )
        return payload

    payload["elements"].extend(
        [
            {
                "id": "title",
                "type": "text",
                "text": _validate_ascii_text(_coerce_ascii_text(call_data["title"]).upper())[:14],
                "font": "small",
                "color": call_data["title_color"],
                "display": DISPLAY_FRONT,
                "align": "top_mid",
                "x": 0,
                "y": 0,
                "width": 72,
            },
            _apply_timeout(call_data, {
                "id": "condition",
                "type": "text",
                "text": condition[:14],
                "font": "tiny",
                "color": call_data["color"],
                "display": DISPLAY_FRONT,
                "align": "top_left",
                "x": 0,
                "y": 8,
                "width": 72,
            }),
            _apply_timeout(call_data, {
                "id": "temp",
                "type": "text",
                "text": temp_text[:14],
                "font": "small",
                "color": call_data["accent_color"],
                "display": DISPLAY_FRONT,
                "align": "top_left",
                "x": 0,
                "y": 16,
                "width": 72,
            }),
        ]
    )
    return payload


def _build_room_climate_dashboard_payload(
    hass: HomeAssistant, call_data: dict[str, Any]
) -> dict[str, Any]:
    display = call_data["display"]
    temp_state = _get_state(hass, call_data["temperature_entity_id"])
    temperature = _format_state_value(
        temp_state.state, _coerce_ascii_text(temp_state.attributes.get("unit_of_measurement"))
    )
    humidity = None
    if call_data.get("humidity_entity_id"):
        humidity_state = _get_state(hass, call_data["humidity_entity_id"])
        humidity = _format_state_value(
            humidity_state.state,
            _coerce_ascii_text(humidity_state.attributes.get("unit_of_measurement")) or "%",
        )
    payload = _base_payload(call_data)
    title = _validate_ascii_text(_coerce_ascii_text(call_data["title"]).upper())

    if display == DISPLAY_BACK:
        payload["elements"].extend(
            [
                {
                    "id": "title",
                    "type": "text",
                    "text": title,
                    "font": "bold",
                    "color": call_data["title_color"],
                    "display": DISPLAY_BACK,
                    "align": "top_left",
                    "x": 4,
                    "y": 4,
                    "width": 152,
                },
                _apply_timeout(call_data, {
                    "id": "temperature",
                    "type": "text",
                    "text": f"TEMP: {temperature}"[:72],
                    "font": "large",
                    "color": call_data["accent_color"],
                    "display": DISPLAY_BACK,
                    "align": "top_left",
                    "x": 4,
                    "y": 26,
                    "width": 152,
                }),
            ]
        )
        if humidity:
            payload["elements"].append(
                _apply_timeout(call_data, {
                    "id": "humidity",
                    "type": "text",
                    "text": f"HUMID: {humidity}"[:72],
                    "font": "normal",
                    "color": call_data["color"],
                    "display": DISPLAY_BACK,
                    "align": "top_left",
                    "x": 4,
                    "y": 60,
                    "width": 152,
                })
            )
        return payload

    payload["elements"].extend(
        [
            {
                "id": "title",
                "type": "text",
                "text": title[:14],
                "font": "small",
                "color": call_data["title_color"],
                "display": DISPLAY_FRONT,
                "align": "top_mid",
                "x": 0,
                "y": 0,
                "width": 72,
            },
            _apply_timeout(call_data, {
                "id": "temperature",
                "type": "text",
                "text": temperature[:14],
                "font": "small",
                "color": call_data["accent_color"],
                "display": DISPLAY_FRONT,
                "align": "top_left",
                "x": 0,
                "y": 10,
                "width": 72,
            }),
        ]
    )
    if humidity:
        payload["elements"].append(
            _apply_timeout(call_data, {
                "id": "humidity",
                "type": "text",
                "text": humidity[:14],
                "font": "tiny",
                "color": call_data["color"],
                "display": DISPLAY_FRONT,
                "align": "top_left",
                "x": 0,
                "y": 20,
                "width": 72,
            })
        )
    return payload


def _build_progress_card_payload(hass: HomeAssistant, call_data: dict[str, Any]) -> dict[str, Any]:
    display = call_data["display"]
    state = _get_state(hass, call_data["entity_id"])
    try:
        percent = int(round(float(state.state)))
    except (TypeError, ValueError):
        raise ServiceValidationError(
            f"Entity {call_data['entity_id']} state is not a numeric percentage"
        )
    percent = max(0, min(100, percent))
    label = _validate_ascii_text(
        _coerce_ascii_text(call_data.get("label") or state.name or "PROGRESS").upper()
    )
    value_text = _validate_ascii_text(f"{percent}%")
    payload = _base_payload(call_data)

    if display == DISPLAY_BACK:
        bar_width = 144
        fill_width = max(2, round(bar_width * percent / 100)) if percent > 0 else 0
        payload["elements"].extend(
            [
                {
                    "id": "label",
                    "type": "text",
                    "text": label[:18],
                    "font": "bold",
                    "color": call_data["title_color"],
                    "display": DISPLAY_BACK,
                    "align": "top_left",
                    "x": 8,
                    "y": 8,
                    "width": 144,
                },
                _apply_timeout(call_data, {
                    "id": "value",
                    "type": "text",
                    "text": value_text,
                    "font": "large",
                    "color": call_data["accent_color"],
                    "display": DISPLAY_BACK,
                    "align": "top_left",
                    "x": 8,
                    "y": 30,
                    "width": 80,
                }),
                _apply_timeout(call_data, {
                    "id": "track",
                    "type": "rectangle",
                    "display": DISPLAY_BACK,
                    "x": 8,
                    "y": 62,
                    "width": bar_width,
                    "height": 12,
                    "radius": 3,
                    "fill": "solid",
                    "fill_colors": [call_data["track_color"]],
                    "border_width": 0,
                }),
            ]
        )
        if fill_width > 0:
            payload["elements"].append(
                _apply_timeout(call_data, {
                    "id": "fill",
                    "type": "rectangle",
                    "display": DISPLAY_BACK,
                    "x": 8,
                    "y": 62,
                    "width": fill_width,
                    "height": 12,
                    "radius": 3,
                    "fill": "solid",
                    "fill_colors": [call_data["accent_color"]],
                    "border_width": 0,
                })
            )
        return payload

    bar_width = 68
    fill_width = max(1, round(bar_width * percent / 100)) if percent > 0 else 0
    payload["elements"].extend(
        [
            {
                "id": "label",
                "type": "text",
                "text": label[:14],
                "font": "small",
                "color": call_data["title_color"],
                "display": DISPLAY_FRONT,
                "align": "top_mid",
                "x": 0,
                "y": 0,
                "width": 72,
            },
            _apply_timeout(call_data, {
                "id": "value",
                "type": "text",
                "text": value_text,
                "font": "small",
                "color": call_data["accent_color"],
                "display": DISPLAY_FRONT,
                "align": "top_mid",
                "x": 0,
                "y": 10,
                "width": 72,
            }),
            _apply_timeout(call_data, {
                "id": "track",
                "type": "rectangle",
                "display": DISPLAY_FRONT,
                "x": 2,
                "y": 24,
                "width": bar_width,
                "height": 6,
                "radius": 2,
                "fill": "solid",
                "fill_colors": [call_data["track_color"]],
                "border_width": 0,
            }),
        ]
    )
    if fill_width > 0:
        payload["elements"].append(
            _apply_timeout(call_data, {
                "id": "fill",
                "type": "rectangle",
                "display": DISPLAY_FRONT,
                "x": 2,
                "y": 24,
                "width": fill_width,
                "height": 6,
                "radius": 2,
                "fill": "solid",
                "fill_colors": [call_data["accent_color"]],
                "border_width": 0,
            })
        )
    return payload


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

ENTITY_DASHBOARD_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("label"): cv.string,
        vol.Optional("attribute"): cv.string,
    }
)

DRAW_ENTITY_DASHBOARD_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_APPLICATION_NAME, default=DEFAULT_APPLICATION_NAME): cv.string,
        vol.Required("title"): vol.All(cv.string, _validate_ascii_text),
        vol.Required("entities"): vol.All(
            [ENTITY_DASHBOARD_ITEM_SCHEMA], vol.Length(min=1, max=4)
        ),
        vol.Optional("display", default=DISPLAY_BACK): vol.In(DISPLAY_NAMES),
        vol.Optional("color", default="#FFFFFFFF"): COLOR_HEX_PATTERN,
        vol.Optional("title_color", default="#FFFFFFFF"): COLOR_HEX_PATTERN,
        vol.Optional(ATTR_LED_NOTIFICATION_COLOR): COLOR_HEX_PATTERN,
        vol.Optional("priority", default=DEFAULT_DRAW_PRIORITY): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
        vol.Optional("clear_before_draw", default=True): cv.boolean,
    }
)

ENABLE_LIVE_ENTITY_DASHBOARD_SERVICE_SCHEMA = DRAW_ENTITY_DASHBOARD_SERVICE_SCHEMA

BIND_BUTTON_ACTION_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required("button"): cv.string,
        vol.Optional("action", default="PRESS"): cv.string,
        vol.Required("service"): cv.string,
        vol.Optional("service_data", default={}): dict,
    }
)

CLEAR_BUTTON_ACTIONS_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional("button"): cv.string,
        vol.Optional("action"): cv.string,
    }
)

WEATHER_DASHBOARD_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_APPLICATION_NAME, default=DEFAULT_APPLICATION_NAME): cv.string,
        vol.Required("weather_entity_id"): cv.entity_id,
        vol.Optional("title", default="WEATHER"): vol.All(cv.string, _validate_ascii_text),
        vol.Optional("display", default=DISPLAY_BACK): vol.In(DISPLAY_NAMES),
        vol.Optional("color", default="#FFFFFFFF"): COLOR_HEX_PATTERN,
        vol.Optional("title_color", default="#FFFFFFFF"): COLOR_HEX_PATTERN,
        vol.Optional("accent_color", default="#00FFCCFF"): COLOR_HEX_PATTERN,
        vol.Optional(ATTR_LED_NOTIFICATION_COLOR): COLOR_HEX_PATTERN,
        vol.Optional("priority", default=DEFAULT_DRAW_PRIORITY): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
        vol.Optional("clear_before_draw", default=True): cv.boolean,
    }
)

ROOM_CLIMATE_DASHBOARD_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_APPLICATION_NAME, default=DEFAULT_APPLICATION_NAME): cv.string,
        vol.Required("temperature_entity_id"): cv.entity_id,
        vol.Optional("humidity_entity_id"): cv.entity_id,
        vol.Optional("title", default="CLIMATE"): vol.All(cv.string, _validate_ascii_text),
        vol.Optional("display", default=DISPLAY_BACK): vol.In(DISPLAY_NAMES),
        vol.Optional("color", default="#FFFFFFFF"): COLOR_HEX_PATTERN,
        vol.Optional("title_color", default="#FFFFFFFF"): COLOR_HEX_PATTERN,
        vol.Optional("accent_color", default="#00FFCCFF"): COLOR_HEX_PATTERN,
        vol.Optional(ATTR_LED_NOTIFICATION_COLOR): COLOR_HEX_PATTERN,
        vol.Optional("priority", default=DEFAULT_DRAW_PRIORITY): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
        vol.Optional("clear_before_draw", default=True): cv.boolean,
    }
)

PROGRESS_CARD_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_APPLICATION_NAME, default=DEFAULT_APPLICATION_NAME): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("label"): cv.string,
        vol.Optional("display", default=DISPLAY_FRONT): vol.In(DISPLAY_NAMES),
        vol.Optional("title_color", default="#FFFFFFFF"): COLOR_HEX_PATTERN,
        vol.Optional("accent_color", default="#00FF00FF"): COLOR_HEX_PATTERN,
        vol.Optional("track_color", default="#333333FF"): COLOR_HEX_PATTERN,
        vol.Optional(ATTR_LED_NOTIFICATION_COLOR): COLOR_HEX_PATTERN,
        vol.Optional("priority", default=DEFAULT_DRAW_PRIORITY): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
        vol.Optional("clear_before_draw", default=True): cv.boolean,
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
        vol.Required("volume"): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=MAX_VOLUME),
            _validate_step_5,
        ),
        vol.Optional("silent", default=True): cv.boolean,
    }
)

SEND_INPUT_COMMAND_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required("key"): vol.In(INPUT_KEYS),
    }
)

APP_ID_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_APP_ID): APP_ID,
    }
)

QUIT_APP_SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string})

INSTALL_APP_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required("path"): cv.string,
        vol.Optional("launch", default=False): cv.boolean,
    }
)

SET_APP_SETTINGS_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_APP_ID): APP_ID,
        vol.Required("values"): dict,
        vol.Optional("merge", default=True): cv.boolean,
    }
)

_T = TypeVar("_T")


async def _async_call_api(awaitable: Awaitable[_T]) -> _T:
    """Surface BUSY Bar API errors to the service caller."""

    try:
        return await awaitable
    except BusyBarApiError as err:
        raise HomeAssistantError(str(err)) from err


def _merge_settings(current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_settings(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_app_package(hass: HomeAssistant, raw_path: str) -> bytes:
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(hass.config.path(raw_path))
    if not hass.config.is_allowed_path(str(path)):
        raise ServiceValidationError(
            f"{path} is not in an allowed directory; add it to allowlist_external_dirs"
        )
    if not path.is_file():
        raise ServiceValidationError(f"App package not found: {path}")
    if path.stat().st_size > MAX_APP_PACKAGE_BYTES:
        raise ServiceValidationError(f"App package is too large: {path}")
    return path.read_bytes()


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

    async def async_render_live_entity_dashboard(call_data: dict[str, Any]) -> None:
        payload = _build_entity_dashboard_payload(hass, call_data)
        if call_data["clear_before_draw"]:
            await client.async_clear(call_data[ATTR_APPLICATION_NAME])
        await client.async_draw(payload)

    button_actions = ButtonActionRegistry()

    async def async_handle_button_action(button: str, action: str) -> None:
        for binding in button_actions.matching(button, action):
            try:
                domain, service = binding["service"].split(".", 1)
            except ValueError:
                LOGGER.warning("Ignoring invalid Busy Bar button binding: %s", binding["service"])
                continue
            await hass.services.async_call(
                domain,
                service,
                dict(binding["service_data"]),
                blocking=False,
            )

    live_dashboard = LiveDashboardController(hass, async_render_live_entity_dashboard)
    button_listener = ButtonEventListener(
        hass,
        client,
        entry.entry_id,
        entry.title,
        async_handle_button_action,
    )
    button_listener.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = BusyBarRuntimeData(
        client=client,
        coordinator=coordinator,
        live_dashboard=live_dashboard,
        button_actions=button_actions,
        button_listener=button_listener,
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
    runtime_data = domain_data.pop(entry.entry_id, None)
    if runtime_data is not None:
        runtime_data.live_dashboard.disable()
        await runtime_data.button_listener.stop()

    remaining_entries = [key for key in domain_data if key != DATA_SERVICES_REGISTERED]
    if not remaining_entries:
        for service_name in (
            SERVICE_BIND_BUTTON_ACTION,
            SERVICE_CLEAR_BUTTON_ACTIONS,
            SERVICE_DRAW_TEXT,
            SERVICE_DRAW_DASHBOARD,
            SERVICE_DRAW_ENTITY_DASHBOARD,
            SERVICE_DRAW_WEATHER_DASHBOARD,
            SERVICE_DRAW_ROOM_CLIMATE_DASHBOARD,
            SERVICE_DRAW_PROGRESS_CARD,
            SERVICE_ENABLE_LIVE_ENTITY_DASHBOARD,
            SERVICE_CLEAR_DISPLAY,
            SERVICE_DISABLE_LIVE_DASHBOARD,
            SERVICE_SEND_INPUT_COMMAND,
            SERVICE_SET_BRIGHTNESS,
            SERVICE_SET_VOLUME,
            SERVICE_LAUNCH_APP,
            SERVICE_QUIT_APP,
            SERVICE_DELETE_APP,
            SERVICE_INSTALL_APP,
            SERVICE_GET_APP_SETTINGS,
            SERVICE_SET_APP_SETTINGS,
            SERVICE_RESET_APP_SETTINGS,
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

    async def async_draw_entity_dashboard(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        payload = _build_entity_dashboard_payload(hass, dict(call.data))

        if call.data["clear_before_draw"]:
            await runtime_data.client.async_clear(call.data[ATTR_APPLICATION_NAME])
        await runtime_data.client.async_draw(payload)
        await runtime_data.coordinator.async_request_refresh()

    async def async_draw_weather_dashboard(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        payload = _build_weather_dashboard_payload(hass, dict(call.data))

        if call.data["clear_before_draw"]:
            await runtime_data.client.async_clear(call.data[ATTR_APPLICATION_NAME])
        await runtime_data.client.async_draw(payload)
        await runtime_data.coordinator.async_request_refresh()

    async def async_draw_room_climate_dashboard(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        payload = _build_room_climate_dashboard_payload(hass, dict(call.data))

        if call.data["clear_before_draw"]:
            await runtime_data.client.async_clear(call.data[ATTR_APPLICATION_NAME])
        await runtime_data.client.async_draw(payload)
        await runtime_data.coordinator.async_request_refresh()

    async def async_draw_progress_card(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        payload = _build_progress_card_payload(hass, dict(call.data))

        if call.data["clear_before_draw"]:
            await runtime_data.client.async_clear(call.data[ATTR_APPLICATION_NAME])
        await runtime_data.client.async_draw(payload)
        await runtime_data.coordinator.async_request_refresh()

    async def async_enable_live_entity_dashboard(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        await runtime_data.live_dashboard.enable(dict(call.data))

    async def async_disable_live_dashboard(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        runtime_data.live_dashboard.disable()

    async def async_bind_button_action(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        runtime_data.button_actions.bind(
            call.data["button"],
            call.data["action"],
            call.data["service"],
            call.data["service_data"],
        )

    async def async_clear_button_actions(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        runtime_data.button_actions.clear(
            call.data.get("button"),
            call.data.get("action"),
        )

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

    async def async_send_input_command(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        await runtime_data.client.async_send_input_key(call.data["key"])
        await runtime_data.coordinator.async_request_refresh()

    async def async_launch_app(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        await _async_call_api(runtime_data.client.async_launch_app(call.data[ATTR_APP_ID]))
        await runtime_data.coordinator.async_request_refresh()

    async def async_quit_app(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        await _async_call_api(runtime_data.client.async_quit_app())
        await runtime_data.coordinator.async_request_refresh()

    async def async_delete_app(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        await _async_call_api(runtime_data.client.async_delete_app(call.data[ATTR_APP_ID]))
        await runtime_data.coordinator.async_request_refresh()

    async def async_install_app(call: ServiceCall) -> ServiceResponse:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        package = await hass.async_add_executor_job(_read_app_package, hass, call.data["path"])
        staged = await _async_call_api(runtime_data.client.async_stage_app(package))
        install_key = staged.get("install_key")
        if not isinstance(install_key, int):
            raise HomeAssistantError("BUSY Bar did not return an install key for the app package")
        await _async_call_api(runtime_data.client.async_install_app(install_key))

        app = staged.get("staged") or {}
        if call.data["launch"] and app.get("id"):
            await _async_call_api(runtime_data.client.async_launch_app(app["id"]))
        await runtime_data.coordinator.async_request_refresh()
        return {"app": app, "replaced": staged.get("installed")}

    async def async_get_app_settings(call: ServiceCall) -> ServiceResponse:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        return await _async_call_api(
            runtime_data.client.async_get_app_settings(call.data[ATTR_APP_ID])
        )

    async def async_set_app_settings(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        app_id = call.data[ATTR_APP_ID]
        # The device replaces the whole document and requires a matching version,
        # so always start from the current document.
        current = await _async_call_api(runtime_data.client.async_get_app_settings(app_id))
        values = call.data["values"]
        if call.data["merge"]:
            values = _merge_settings(current.get("values") or {}, values)
        await _async_call_api(
            runtime_data.client.async_set_app_settings(
                app_id,
                {"version": current.get("version"), "values": values},
            )
        )

    async def async_reset_app_settings(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass, call.data.get(ATTR_ENTRY_ID))
        await _async_call_api(runtime_data.client.async_reset_app_settings(call.data[ATTR_APP_ID]))

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
        SERVICE_DRAW_ENTITY_DASHBOARD,
        async_draw_entity_dashboard,
        schema=DRAW_ENTITY_DASHBOARD_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ENABLE_LIVE_ENTITY_DASHBOARD,
        async_enable_live_entity_dashboard,
        schema=ENABLE_LIVE_ENTITY_DASHBOARD_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DISABLE_LIVE_DASHBOARD,
        async_disable_live_dashboard,
        schema=vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DRAW_WEATHER_DASHBOARD,
        async_draw_weather_dashboard,
        schema=WEATHER_DASHBOARD_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DRAW_ROOM_CLIMATE_DASHBOARD,
        async_draw_room_climate_dashboard,
        schema=ROOM_CLIMATE_DASHBOARD_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DRAW_PROGRESS_CARD,
        async_draw_progress_card,
        schema=PROGRESS_CARD_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_BIND_BUTTON_ACTION,
        async_bind_button_action,
        schema=BIND_BUTTON_ACTION_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_BUTTON_ACTIONS,
        async_clear_button_actions,
        schema=CLEAR_BUTTON_ACTIONS_SERVICE_SCHEMA,
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
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_INPUT_COMMAND,
        async_send_input_command,
        schema=SEND_INPUT_COMMAND_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LAUNCH_APP,
        async_launch_app,
        schema=APP_ID_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_QUIT_APP,
        async_quit_app,
        schema=QUIT_APP_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_APP,
        async_delete_app,
        schema=APP_ID_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_INSTALL_APP,
        async_install_app,
        schema=INSTALL_APP_SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_APP_SETTINGS,
        async_get_app_settings,
        schema=APP_ID_SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_APP_SETTINGS,
        async_set_app_settings,
        schema=SET_APP_SETTINGS_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_APP_SETTINGS,
        async_reset_app_settings,
        schema=APP_ID_SERVICE_SCHEMA,
    )

    domain_data[DATA_SERVICES_REGISTERED] = True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: Any,
) -> bool:
    """Allow removing the device from the device registry."""

    return True