from __future__ import annotations

from collections.abc import Mapping
import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

import aiohttp

from .const import DEFAULT_BASE_URL

LOGGER = logging.getLogger(__name__)


class BusyBarApiError(Exception):
    """Base Busy Bar API error."""


class BusyBarAuthError(BusyBarApiError):
    """Busy Bar authentication failure."""


def normalize_base_url(base_url: str) -> str:
    """Normalize a BUSY Bar base URL.

    The BUSY Bar docs use `/api` for USB and LAN endpoints, and `/busybar`
    for the public cloud endpoint. If the user provides only scheme + host,
    fill in the expected path automatically.
    """

    raw = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Base URL must include a scheme and host")

    if parsed.path and parsed.path != "/":
        return raw

    default_path = "/busybar" if parsed.netloc == "api.busy.app" else "/api"
    return raw + default_path


class BusyBarApiClient:
    """Async client for the BUSY Bar HTTP API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        token: str | None,
    ) -> None:
        self._session = session
        self._base_url = normalize_base_url(base_url)
        self._token = token.strip() if token else None

    @property
    def base_url(self) -> str:
        return self._base_url

    def _build_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self._base_url}{path}"

    def _build_ws_url(self, path: str) -> str:
        parsed = urlparse(self._build_url(path))
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return urlunparse(parsed._replace(scheme=scheme))

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if not self._token:
            return headers

        parsed = urlparse(self._base_url)
        if parsed.netloc == "api.busy.app":
            headers["Authorization"] = f"Bearer {self._token}"
        else:
            headers["X-API-Token"] = self._token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_payload: Mapping[str, Any] | None = None,
        data: bytes | None = None,
    ) -> dict[str, Any]:
        url = self._build_url(path)
        headers = self._headers()
        if data is not None:
            headers["Content-Type"] = "application/octet-stream"
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_payload,
                data=data,
            ) as response:
                if response.status in (401, 403):
                    raise BusyBarAuthError("Authentication failed")

                if response.status >= 400:
                    detail = await response.text()
                    raise BusyBarApiError(
                        f"HTTP {response.status} from BUSY Bar API: {detail.strip()}"
                    )

                if response.content_type != "application/json":
                    return {}
                return await response.json()
        except BusyBarApiError:
            raise
        except aiohttp.ClientError as err:
            raise BusyBarApiError(f"Request failed: {err}") from err
        except TimeoutError as err:
            raise BusyBarApiError("Timed out talking to BUSY Bar") from err

    async def async_get_status(self) -> dict[str, Any]:
        return await self._request("GET", "/status")

    async def async_get_display_brightness(self) -> dict[str, Any]:
        return await self._request("GET", "/display/brightness")

    async def async_get_audio_volume(self) -> dict[str, Any]:
        return await self._request("GET", "/audio/volume")

    async def async_get_name(self) -> dict[str, Any]:
        return await self._request("GET", "/name")

    async def async_set_name(self, name: str) -> dict[str, Any]:
        return await self._request("POST", "/name", json_payload={"name": name})

    async def async_get_busy_snapshot(self) -> dict[str, Any]:
        return await self._request("GET", "/busy/snapshot")

    async def async_set_busy_snapshot(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", "/busy/snapshot", json_payload=snapshot)

    async def async_set_busy_theme(self, theme: str) -> dict[str, Any]:
        current = await self.async_get_busy_snapshot()
        snapshot = current.get("snapshot")
        if not isinstance(snapshot, dict):
            raise BusyBarApiError("BUSY snapshot payload is missing snapshot object")

        busy_settings = snapshot.get("busy_bar_settings")
        if not isinstance(busy_settings, dict):
            raise BusyBarApiError("BUSY snapshot payload is missing busy_bar_settings")

        busy_settings["theme"] = theme
        return await self.async_set_busy_snapshot(current)

    async def async_send_input_key(self, key: str) -> dict[str, Any]:
        return await self._request("POST", "/input", params={"key": key})

    async def async_list_apps(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/apps/list")
        apps = result.get("apps")
        return apps if isinstance(apps, list) else []

    async def async_launch_app(self, app_id: str) -> dict[str, Any]:
        return await self._request("POST", "/apps/launch", params={"app_id": app_id})

    async def async_quit_app(self) -> dict[str, Any]:
        return await self._request("POST", "/apps/quit")

    async def async_delete_app(self, app_id: str) -> dict[str, Any]:
        return await self._request("DELETE", "/apps", params={"app_id": app_id})

    async def async_stage_app(self, package: bytes) -> dict[str, Any]:
        return await self._request("POST", "/apps/stage", data=package)

    async def async_install_app(self, install_key: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/apps/install",
            params={"install_key": install_key},
        )

    async def async_get_app_settings(self, app_id: str) -> dict[str, Any]:
        return await self._request("GET", "/apps/settings", params={"app_id": app_id})

    async def async_set_app_settings(
        self,
        app_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            "/apps/settings",
            params={"app_id": app_id},
            json_payload=document,
        )

    async def async_reset_app_settings(self, app_id: str) -> dict[str, Any]:
        return await self._request("DELETE", "/apps/settings", params={"app_id": app_id})

    async def async_get_snapshot(self) -> dict[str, Any]:
        status, brightness, audio, name = await asyncio.gather(
            self.async_get_status(),
            self.async_get_display_brightness(),
            self.async_get_audio_volume(),
            self.async_get_name(),
        )

        try:
            busy = await self.async_get_busy_snapshot()
        except BusyBarApiError:
            busy = {}

        # The apps API needs firmware 1.3.1+ and is not available over the cloud endpoint.
        try:
            apps: list[dict[str, Any]] | None = await self.async_list_apps()
        except BusyBarAuthError:
            raise
        except BusyBarApiError:
            apps = None

        return {
            **status,
            "display": {"brightness": brightness.get("value")},
            "audio": {"volume": audio.get("volume")},
            "name": {"name": name.get("name")},
            "busy": busy if isinstance(busy, dict) else {},
            "apps": apps,
        }

    async def async_draw(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        LOGGER.debug("Drawing on BUSY Bar: %s", payload)
        return await self._request("POST", "/display/draw", json_payload=payload)

    async def async_clear(self, application_name: str | None = None) -> dict[str, Any]:
        params = {"application_name": application_name} if application_name else None
        return await self._request("DELETE", "/display/draw", params=params)

    async def async_set_brightness(self, value: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/display/brightness",
            params={"value": value},
        )

    async def async_set_volume(self, volume: int, silent: bool) -> dict[str, Any]:
        params: dict[str, Any] = {"volume": volume}
        if silent:
            params["silent"] = 1
        return await self._request("POST", "/audio/volume", params=params)

    async def async_stop_audio(self) -> dict[str, Any]:
        return await self._request("DELETE", "/audio/play")

    async def async_status_ws_messages(self):
        ws_url = self._build_ws_url("/status/ws")
        async with self._session.ws_connect(
            ws_url,
            headers=self._headers(),
            heartbeat=30,
        ) as websocket:
            await websocket.send_json({"enable": True})
            async for message in websocket:
                if message.type == aiohttp.WSMsgType.TEXT:
                    try:
                        yield json.loads(message.data)
                    except json.JSONDecodeError:
                        LOGGER.debug("Ignoring non-JSON BUSY Bar websocket message: %s", message.data)
                elif message.type == aiohttp.WSMsgType.ERROR:
                    raise BusyBarApiError("BUSY Bar websocket stream error")