from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .client import BusyBarApiClient, BusyBarApiError, BusyBarAuthError, normalize_base_url
from .const import CONF_BASE_URL, CONF_POLL_INTERVAL, DEFAULT_BASE_URL, DEFAULT_NAME, DOMAIN


class BusyBarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BUSY Bar."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized_url = normalize_base_url(user_input[CONF_BASE_URL])
            except ValueError:
                errors[CONF_BASE_URL] = "invalid_url"
            else:
                session = async_get_clientsession(self.hass)
                client = BusyBarApiClient(
                    session,
                    normalized_url,
                    user_input.get(CONF_TOKEN),
                )

                try:
                    status = await client.async_get_status()
                except BusyBarAuthError:
                    errors["base"] = "invalid_auth"
                except BusyBarApiError:
                    errors["base"] = "cannot_connect"
                else:
                    serial_number = status.get("device", {}).get("serial_number")
                    if serial_number:
                        await self.async_set_unique_id(serial_number)
                        self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=user_input[CONF_NAME],
                        data={
                            CONF_NAME: user_input[CONF_NAME],
                            CONF_BASE_URL: normalized_url,
                            CONF_TOKEN: user_input.get(CONF_TOKEN, ""),
                            CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(user_input),
            errors=errors,
        )

    @callback
    def _build_schema(self, user_input: dict[str, Any] | None = None) -> vol.Schema:
        defaults = user_input or {}
        return vol.Schema(
            {
                vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): cv.string,
                vol.Required(
                    CONF_BASE_URL,
                    default=defaults.get(CONF_BASE_URL, DEFAULT_BASE_URL),
                ): cv.string,
                vol.Optional(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): cv.string,
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=defaults.get(CONF_POLL_INTERVAL, 30),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=3600)),
            }
        )