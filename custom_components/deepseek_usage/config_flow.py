"""Config flow for DeepSeek Usage integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class DeepSeekConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DeepSeek Usage."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input["api_key"].strip()

            valid = await self._test_api_key(api_key)
            if valid:
                await self.async_set_unique_id("deepseek_usage_unique")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="DeepSeek Usage",
                    data={"api_key": api_key},
                )
            else:
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("api_key"): str,
            }),
            errors=errors,
        )

    async def _test_api_key(self, api_key: str) -> bool:
        """Test if API key is valid."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.deepseek.com/user/balance",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return DeepSeekOptionsFlow(config_entry)


class DeepSeekOptionsFlow(OptionsFlow):
    """Handle options flow for DeepSeek Usage."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        try:
            super().__init__()
        except TypeError:
            super().__init__(config_entry)
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options or {}
        default_scan = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        if not isinstance(default_scan, int):
            default_scan = DEFAULT_SCAN_INTERVAL

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=default_scan,
                ): vol.All(vol.Coerce(int), vol.Range(min=60, max=86400)),
            }),
        )
