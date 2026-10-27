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

EVENT_BUTTON = "busybar_button"

SERVICE_BIND_BUTTON_ACTION = "bind_button_action"
SERVICE_CLEAR_BUTTON_ACTIONS = "clear_button_actions"
SERVICE_CLEAR_DISPLAY = "clear_display"
SERVICE_DRAW_DASHBOARD = "draw_dashboard"
SERVICE_DRAW_ENTITY_DASHBOARD = "draw_entity_dashboard"
SERVICE_DRAW_PROGRESS_CARD = "draw_progress_card"
SERVICE_ENABLE_LIVE_ENTITY_DASHBOARD = "enable_live_entity_dashboard"
SERVICE_DRAW_TEXT = "draw_text"
SERVICE_DRAW_WEATHER_DASHBOARD = "draw_weather_dashboard"
SERVICE_DRAW_ROOM_CLIMATE_DASHBOARD = "draw_room_climate_dashboard"
SERVICE_SEND_INPUT_COMMAND = "send_input_command"
SERVICE_SET_BRIGHTNESS = "set_brightness"
SERVICE_SET_VOLUME = "set_volume"
SERVICE_DISABLE_LIVE_DASHBOARD = "disable_live_dashboard"
SERVICE_LAUNCH_APP = "launch_app"
SERVICE_QUIT_APP = "quit_app"
SERVICE_DELETE_APP = "delete_app"
SERVICE_INSTALL_APP = "install_app"
SERVICE_GET_APP_SETTINGS = "get_app_settings"
SERVICE_SET_APP_SETTINGS = "set_app_settings"
SERVICE_RESET_APP_SETTINGS = "reset_app_settings"

ATTR_APP_ID = "app_id"

INPUT_KEYS = (
    "up",
    "down",
    "ok",
    "back",
    "start",
    "busy",
    "custom",
    "off",
    "apps",
    "settings",
)

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
DISPLAY_FONT_SUPERSCRIPT = "superscript"

DISPLAY_FONTS = (
    DISPLAY_FONT_TINY,
    DISPLAY_FONT_SMALL,
    DISPLAY_FONT_NORMAL,
    DISPLAY_FONT_CONDENSED,
    DISPLAY_FONT_BOLD,
    DISPLAY_FONT_LARGE,
    DISPLAY_FONT_EXTRA_LARGE,
    DISPLAY_FONT_GLOBAL,
    DISPLAY_FONT_SUPERSCRIPT,
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

APP_ID_PATTERN = r"^[a-zA-Z0-9_\-][a-zA-Z0-9_\-.]{0,31}$"

DATA_SERVICES_REGISTERED = "services_registered"