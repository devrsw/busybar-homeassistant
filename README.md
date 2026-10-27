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
- A higher-level dashboard service that renders Home Assistant entity states without raw BUSY Bar payload JSON
- Specialized helpers for weather, room climate, and percent/progress layouts
- A live entity-dashboard mode that redraws automatically when Home Assistant entities change
- BUSY Bar button events exposed into Home Assistant, with optional runtime service bindings
- BUSY timer entities for mode, pause state, time left, current interval, and editable theme
- BUSY input command controls through buttons and a dedicated service
- JavaScript app management (firmware 1.3.1+): list, launch, quit, install, and uninstall apps, and read or change their settings
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

To draw a standalone rectangle, include a `rectangle` element in the payload. Set
`x` and `y` for its position, `width` and `height` for its size, and `fill_colors`
for its RGBA fill color:

```yaml
service: busybar.draw_dashboard
data:
	clear_before_draw: true
	payload:
		application_name: home_assistant
		priority: 80
		elements:
			- id: rectangle
				type: rectangle
				display: front
				x: 4
				y: 8
				width: 56
				height: 20
				radius: 2
				fill: solid
				fill_colors:
					- "#00FF00FF"
```

### `busybar.draw_entity_dashboard`

Build a simple dashboard directly from Home Assistant entity values. The integration reads the entities, formats label/value rows, and generates the BUSY Bar payload for you.

Example:

```yaml
service: busybar.draw_entity_dashboard
data:
	title: HOME
	display: back
	clear_before_draw: true
	entities:
		- entity_id: sensor.living_room_temperature
			label: TEMP
		- entity_id: sensor.office_humidity
			label: HUMID
		- entity_id: weather.home
			label: WEATHER
		- entity_id: sensor.washer_state
			label: WASHER
```

Each entity item supports:

- `entity_id` required
- `label` optional override for the row label
- `attribute` optional attribute name to display instead of the state

### `busybar.draw_weather_dashboard`

Build a weather layout from a Home Assistant `weather.*` entity.

```yaml
service: busybar.draw_weather_dashboard
data:
	weather_entity_id: weather.home
	title: WEATHER
	display: back
```

### `busybar.draw_room_climate_dashboard`

Build a room climate layout from temperature and optional humidity entities.

```yaml
service: busybar.draw_room_climate_dashboard
data:
	title: OFFICE
	temperature_entity_id: sensor.office_temperature
	humidity_entity_id: sensor.office_humidity
	display: back
```

### `busybar.draw_progress_card`

Build a progress card from any Home Assistant entity whose state is a numeric percentage.

```yaml
service: busybar.draw_progress_card
data:
	entity_id: sensor.phone_battery
	label: PHONE
	display: front
```

### `busybar.enable_live_entity_dashboard`

Keep an entity-based dashboard live. The integration subscribes to the listed Home Assistant entities and redraws the BUSY Bar whenever one of them changes.

```yaml
service: busybar.enable_live_entity_dashboard
data:
	title: HOME
	display: back
	entities:
		- entity_id: sensor.living_room_temperature
			label: TEMP
		- entity_id: sensor.office_humidity
			label: HUMID
		- entity_id: weather.home
			label: WEATHER
```

Disable it with:

```yaml
service: busybar.disable_live_dashboard
```

### BUSY Bar button events

The integration listens to the BUSY Bar websocket stream and fires a Home Assistant event named `busybar_button` whenever the device reports a button event.

Event data includes:

- `entry_id`
- `name`
- `button`
- `action`

You can use normal Home Assistant automations to react to those events, or register runtime button bindings with the helper services below.

### `busybar.bind_button_action`

Bind a BUSY Bar button event to a Home Assistant service call for the current runtime.

```yaml
service: busybar.bind_button_action
data:
	button: START
	action: PRESS
	service: light.toggle
	service_data:
		entity_id: light.office_lamp
```

Remove bindings with:

```yaml
service: busybar.clear_button_actions
data:
	button: START
```

### `busybar.set_brightness`

Set display brightness to `auto` or a numeric value from `0` to `100`.

### `busybar.set_volume`

Set device audio volume from `0` to `100` in `5%` increments.

```yaml
service: busybar.set_volume
data:
	volume: 55
	silent: true
```

### `busybar.send_input_command`

Send a BUSY input key command (`up`, `down`, `ok`, `back`, `start`, `busy`, `custom`, `off`, `apps`, or `settings`).

```yaml
service: busybar.send_input_command
data:
	key: start
```

### JavaScript apps

Firmware 1.3.1 made JavaScript apps the official way to build BUSY Bar apps. The apps API only works over USB or LAN, not through the BUSY cloud endpoint. Use the Installed Apps sensor's `apps` attribute to find app IDs.

- `busybar.launch_app` / `busybar.quit_app`: start an installed app or quit the running one
- `busybar.install_app`: upload a `.tgz` or `.tar` package from a path Home Assistant can read (relative paths resolve against the config directory) and optionally launch it; returns the installed app info
- `busybar.delete_app`: uninstall an app (the device keeps its settings)
- `busybar.get_app_settings`: returns the app's settings document as a service response
- `busybar.set_app_settings`: merges `values` into the current settings (set `merge: false` to replace the whole document)
- `busybar.reset_app_settings`: reset every setting to its default

```yaml
service: busybar.set_app_settings
data:
	app_id: com.example.weather
	values:
		units: metric
```

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
- Busy theme as a writable text entity
- Busy timer mode and current interval sensors
- Busy time-left duration sensor and paused-state binary sensor
- Buttons to clear the Home Assistant display namespace and stop audio playback
- Buttons for common BUSY input commands (Start, Busy, Custom, OK, Back)
- Installed Apps sensor (count, with app IDs, names, and versions as attributes), a Launch App select, and a Quit App button, when the apps API is available

## Notes

- The text draw service intentionally starts with text-only rendering because that is the smallest stable control surface for Home Assistant automations.
- The dashboard service is a direct pass-through for BUSY Bar display payloads, so you can build richer layouts in Home Assistant without waiting on dedicated entity types.
- The entity dashboard helper is intentionally simple and text-based. It is meant to cover common status dashboards without forcing you to hand-author BUSY Bar element JSON.
- The specialized helpers are thin layout builders on top of the BUSY Bar draw API. They are meant to cover common automation use cases with less templating.
- Runtime button bindings are not persisted across Home Assistant restarts. Use the `busybar_button` event in automations if you need persistent behavior.
- BUSY Bar text rendering accepts printable ASCII only.
- The `superscript` font (firmware 1.3.1+) is available in `busybar.draw_text` and dashboard payloads.
- The BUSY Bar API does not report which app is running, so the Launch App select shows the app most recently launched from Home Assistant.
- If you configure more than one BUSY Bar, include `entry_id` in service calls to target a specific device.

## Suggested GitHub metadata

- Description: `Local-first Home Assistant integration for BUSY Bar via the official HTTP API`
- Topics: `home-assistant`, `home-assistant-integration`, `hacs`, `busybar`, `busy-bar`, `iot`, `local-polling`, `smart-home`

## HACS publishing notes

- This repository is structured as a HACS custom integration repository.
- To make version selection work cleanly in HACS, publish GitHub releases as you tag versions.