# busybar-homeassistant

Custom Home Assistant integration for BUSY Bar using the official BUSY Bar HTTP API.

Local-first integration for Home Assistant. USB and LAN control work without any BUSY cloud dependency.

[![Open your Home Assistant instance and open the HACS repository dialog with a specific repository pre-filled.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=devrsw&repository=busybar-homeassistant&category=integration)

## What this includes

- Config-entry-based custom integration under `custom_components/busybar`
- Polling sensors for device status, firmware info, API version, and battery charge
- Additional Home Assistant entities for BUSY Bar battery, power, firmware, security, auto-update status, audio volume, device naming, and device controls
- Services for drawing text, clearing the display, setting display brightness, and setting audio volume
- A generic dashboard service that lets Home Assistant send a full BUSY Bar display layout
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

For a fully local setup, use USB or LAN. A BUSY cloud account is not required unless you intentionally use the internet endpoint.

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

### `busybar.draw_dashboard`

Send a full BUSY Bar `DisplayElements` payload from Home Assistant. This is the flexible path for building a custom Busy Bar dashboard from automations, scripts, or template-generated service data.

Example:

```yaml
service: busybar.draw_dashboard
data:
	clear_before_draw: true
	payload:
		application_name: home_assistant
		priority: 80
		elements:
			- id: headline
				type: text
				text: OFFICE
				font: bold
				color: "#FFFFFFFF"
				display: front
				align: top_mid
				x: 0
				y: 2
			- id: temp
				type: text
				text: 72F
				font: large
				color: "#00FFCCFF"
				display: front
				align: center
				x: 0
				y: 6
			- id: bar_bg
				type: rectangle
				display: front
				x: 4
				y: 28
				width: 64
				height: 8
				radius: 2
				fill: solid
				fill_colors:
					- "#333333FF"
			- id: bar_fg
				type: rectangle
				display: front
				x: 4
				y: 28
				width: 48
				height: 8
				radius: 2
				fill: solid
				fill_colors:
					- "#00FF00FF"
```

### `busybar.set_brightness`

Set display brightness to `auto` or a numeric value from `0` to `100`.

### `busybar.set_volume`

Set device audio volume from `0` to `100`.

## Exposed entities

The integration now exposes a wider set of Home Assistant entities backed by the BUSY Bar HTTP API, including:

- Battery charge, voltage, current, and power state
- USB voltage
- Firmware version, branch, target, and firmware security state
- API version and last boot time
- Serial number
- Display brightness as a writable number plus a brightness-mode select
- Auto-update enabled
- Audio volume as a writable number entity
- Device name as a writable text entity
- Buttons to clear the Home Assistant display namespace and stop audio playback

## Notes

- The text draw service intentionally starts with text-only rendering because that is the smallest stable control surface for Home Assistant automations.
- The dashboard service is a direct pass-through for BUSY Bar display payloads, so you can build richer layouts in Home Assistant without waiting on dedicated entity types.
- BUSY Bar text rendering accepts printable ASCII only.
- If you configure more than one BUSY Bar, include `entry_id` in service calls to target a specific device.

## Suggested GitHub metadata

- Description: `Local-first Home Assistant integration for BUSY Bar via the official HTTP API`
- Topics: `home-assistant`, `home-assistant-integration`, `hacs`, `busybar`, `busy-bar`, `iot`, `local-polling`, `smart-home`

## HACS publishing notes

- This repository is structured as a HACS custom integration repository.
- To make version selection work cleanly in HACS, publish GitHub releases as you tag versions.