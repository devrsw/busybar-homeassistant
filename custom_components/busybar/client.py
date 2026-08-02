from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
from urllib.parse import urlparse

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
    ) -> dict[str, Any]:
        url = self._build_url(path)
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_payload,
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