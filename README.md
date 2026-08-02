# busybar-homeassistant

Custom Home Assistant integration for BUSY Bar using the official BUSY Bar HTTP API.

[![Open your Home Assistant instance and open the HACS repository dialog with a specific repository pre-filled.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=devrsw&repository=busybar-homeassistant&category=integration)

## What this includes

- Config-entry-based custom integration under `custom_components/busybar`
- Polling sensors for device status, firmware info, API version, and battery charge
- Services for drawing text, clearing the display, setting display brightness, and setting audio volume
- Support for BUSY Bar over USB, LAN, or the BUSY cloud endpoint

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Open the custom repositories dialog.
3. Add `https://github.com/devrsw/busybar-homeassistant` as an `Integration` repository.
4. Install `BUSY Bar` from HACS.
5. Restart Home Assistant.
6. Go to Settings -> Devices & Services -> Add Integration.
7. Search for `BUSY Bar`.

### Manual

1. Copy `custom_components/busybar` into your Home Assistant config directory.
2. Restart Home Assistant.
3. In Home Assistant, go to Settings -> Devices & Services -> Add Integration.
4. Search for `BUSY Bar`.

## Configuration

Use one of these base URLs:

- USB: `http://10.0.4.20/api`
- LAN: `http://<busy-bar-ip>/api`
- Internet: `https://api.busy.app/busybar`

Authentication rules:

- USB: no token required
- LAN: provide the HTTP API password; the integration sends it as `X-API-Token`
- Internet: provide an API token; the integration sends it as `Authorization: Bearer <token>`

## Services

### `busybar.draw_text`

Draw printable ASCII text on the front or back display.

Example:

```yaml
service: busybar.draw_text
data:
	text: Washer done
	color: "#00FF00FF"
	led_notification_color: "#00FF00FF"
	priority: 80
	duration: 30
```

### `busybar.clear_display`

Clear the integration's display content, or a specific application name.

### `busybar.set_brightness`

Set display brightness to `auto` or a numeric value from `0` to `100`.

### `busybar.set_volume`

Set device audio volume from `0` to `100`.

## Notes

- The text draw service intentionally starts with text-only rendering because that is the smallest stable control surface for Home Assistant automations.
- BUSY Bar text rendering accepts printable ASCII only.
- If you configure more than one BUSY Bar, include `entry_id` in service calls to target a specific device.

## HACS publishing notes

- This repository is structured as a HACS custom integration repository.
- To make version selection work cleanly in HACS, publish GitHub releases as you tag versions.