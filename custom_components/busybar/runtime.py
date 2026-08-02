from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from homeassistant.core import Event, EventStateChangedData, HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event

from .client import BusyBarApiClient, BusyBarApiError
from .const import EVENT_BUTTON

LOGGER = logging.getLogger(__name__)

RenderCallback = Callable[[dict[str, Any]], Awaitable[None]]
ButtonCallback = Callable[[str, str], Awaitable[None]]


class LiveDashboardController:
    """Manage one active live entity dashboard per BUSY Bar entry."""

    def __init__(self, hass: HomeAssistant, render_callback: RenderCallback) -> None:
        self._hass = hass
        self._render_callback = render_callback
        self._unsubscribe = None
        self._config: dict[str, Any] | None = None

    @property
    def is_enabled(self) -> bool:
        return self._config is not None

    async def enable(self, config: dict[str, Any]) -> None:
        self.disable()
        self._config = dict(config)
        entity_ids = [item["entity_id"] for item in config["entities"]]
        self._unsubscribe = async_track_state_change_event(
            self._hass,
            entity_ids,
            self._handle_state_change,
        )
        await self._render_callback(self._config)

    def disable(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._config = None

    async def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        del event
        if self._config is None:
            return
        await self._render_callback(self._config)


class ButtonActionRegistry:
    """Store runtime button-action bindings for a BUSY Bar entry."""

    def __init__(self) -> None:
        self._bindings: list[dict[str, Any]] = []

    def bind(self, button: str, action: str, service: str, service_data: dict[str, Any]) -> None:
        self._bindings.append(
            {
                "button": button.upper(),
                "action": action.upper(),
                "service": service,
                "service_data": dict(service_data),
            }
        )

    def clear(self, button: str | None = None, action: str | None = None) -> None:
        if button is None and action is None:
            self._bindings.clear()
            return

        button = button.upper() if button else None
        action = action.upper() if action else None
        self._bindings = [
            binding
            for binding in self._bindings
            if not (
                (button is None or binding["button"] == button)
                and (action is None or binding["action"] == action)
            )
        ]

    def matching(self, button: str, action: str) -> list[dict[str, Any]]:
        button = button.upper()
        action = action.upper()
        return [
            binding
            for binding in self._bindings
            if binding["button"] == button and binding["action"] == action
        ]


class ButtonEventListener:
    """Listen to the BUSY Bar websocket stream and surface button events."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: BusyBarApiClient,
        entry_id: str,
        entry_title: str,
        callback: ButtonCallback,
    ) -> None:
        self._hass = hass
        self._client = client
        self._entry_id = entry_id
        self._entry_title = entry_title
        self._callback = callback
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = self._hass.async_create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        backoff = 1.0
        while True:
            try:
                async for message in self._client.async_status_ws_messages():
                    backoff = 1.0
                    for button, action in _extract_button_events(message):
                        self._hass.bus.async_fire(
                            EVENT_BUTTON,
                            {
                                "entry_id": self._entry_id,
                                "name": self._entry_title,
                                "button": button,
                                "action": action,
                            },
                        )
                        await self._callback(button, action)
            except asyncio.CancelledError:
                raise
            except BusyBarApiError as err:
                LOGGER.debug("BUSY Bar websocket disconnected: %s", err)
            except Exception:
                LOGGER.exception("Unexpected BUSY Bar websocket listener error")

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


def _extract_button_events(message: Any) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    if not isinstance(message, dict):
        return events
    for update in message.get("updates", []):
        if not isinstance(update, dict):
            continue
        button_event = update.get("input", {}).get("button_event")
        if not isinstance(button_event, dict):
            continue
        button = button_event.get("button")
        action = button_event.get("action") or "PRESS"
        if isinstance(button, str) and isinstance(action, str):
            events.append((button.upper(), action.upper()))
    return events