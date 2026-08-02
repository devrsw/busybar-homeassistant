from __future__ import annotations

from datetime import timedelta

DOMAIN = "busybar"
DEFAULT_NAME = "BUSY Bar"
DEFAULT_BASE_URL = "http://10.0.4.20/api"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
DEFAULT_APPLICATION_NAME = "home_assistant"
DEFAULT_DRAW_PRIORITY = 80

CONF_BASE_URL = "base_url"
CONF_POLL_INTERVAL = "poll_interval"

ATTR_ENTRY_ID = "entry_id"
ATTR_APPLICATION_NAME = "application_name"
ATTR_DURATION = "duration"
ATTR_LED_NOTIFICATION_COLOR = "led_notification_color"
ATTR_PAYLOAD = "payload"

SERVICE_CLEAR_DISPLAY = "clear_display"
SERVICE_DRAW_DASHBOARD = "draw_dashboard"
SERVICE_DRAW_TEXT = "draw_text"
SERVICE_SET_BRIGHTNESS = "set_brightness"
SERVICE_SET_VOLUME = "set_volume"

DISPLAY_FRONT = "front"
DISPLAY_BACK = "back"

DISPLAY_FONT_TINY = "tiny"
DISPLAY_FONT_SMALL = "small"
DISPLAY_FONT_NORMAL = "normal"
DISPLAY_FONT_CONDENSED = "condensed"
DISPLAY_FONT_BOLD = "bold"
DISPLAY_FONT_LARGE = "large"
DISPLAY_FONT_EXTRA_LARGE = "extra_large"
DISPLAY_FONT_GLOBAL = "global"

DISPLAY_FONTS = (
    DISPLAY_FONT_TINY,
    DISPLAY_FONT_SMALL,
    DISPLAY_FONT_NORMAL,
    DISPLAY_FONT_CONDENSED,
    DISPLAY_FONT_BOLD,
    DISPLAY_FONT_LARGE,
    DISPLAY_FONT_EXTRA_LARGE,
    DISPLAY_FONT_GLOBAL,
)

DISPLAY_ALIGNMENTS = (
    "top_left",
    "top_mid",
    "top_right",
    "mid_left",
    "center",
    "mid_right",
    "bottom_left",
    "bottom_mid",
    "bottom_right",
)

DISPLAY_NAMES = (DISPLAY_FRONT, DISPLAY_BACK)

MAX_BRIGHTNESS = 100
MAX_VOLUME = 100

DATA_SERVICES_REGISTERED = "services_registered"