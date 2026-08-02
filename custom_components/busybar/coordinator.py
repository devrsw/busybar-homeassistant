from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import BusyBarApiClient, BusyBarApiError, BusyBarAuthError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

LOGGER = logging.getLogger(__name__)


class BusyBarDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch BUSY Bar status data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        client: BusyBarApiClient,
        config_entry: ConfigEntry,
        update_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_snapshot()
        except BusyBarAuthError as err:
            raise ConfigEntryAuthFailed from err
        except BusyBarApiError as err:
            raise UpdateFailed(str(err)) from err