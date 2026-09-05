"""Config flow for DeepSeek Usage integration."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import BALANCE_API_URL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required("api_key"): str})


def _unique_id_for(api_key: str) -> str:
    """Derive a stable unique id from the API key (multi-account friendly)."""
    return "deepseek_" + hashlib.sha1(api_key.encode()).hexdigest()[:12]


class DeepSeekConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DeepSeek Usage."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input["api_key"].strip()
            error = await self._test_api_key(api_key)
            if error is None:
                await self.async_set_unique_id(_unique_id_for(api_key))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="DeepSeek Usage",
                    data={"api_key": api_key},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def _test_api_key(self, api_key: str) -> str | None:
        """Validate the key; return an error key or None on success.

        Network failures are reported as cannot_connect instead of blaming
        the key.
        """
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                BALANCE_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 401:
                    return "invalid_auth"
                if response.status == 200:
                    return None
                return "cannot_connect"
        except (TimeoutError, aiohttp.ClientError):
            return "cannot_connect"

    async def async_step_reauth(self, entry_data) -> ConfigFlowResult:
        """Start reauthentication after the coordinator reported a bad key."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a (new) API key and store it on success."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if user_input is not None and entry is not None:
            api_key = user_input["api_key"].strip()
            error = await self._test_api_key(api_key)
            if error is None:
                new_unique_id = _unique_id_for(api_key)
                for other in self._async_current_entries():
                    if other.entry_id != entry.entry_id and other.unique_id == new_unique_id:
                        return self.async_abort(reason="already_configured")
                self.hass.config_entries.async_update_entry(
                    entry, data={"api_key": api_key}, unique_id=new_unique_id
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("api_key"): str}),
            errors=errors,
            description_placeholders={"name": entry.title if entry else DOMAIN},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DeepSeekOptionsFlow:
        """Get the options flow for this handler."""
        return DeepSeekOptionsFlow()


class DeepSeekOptionsFlow(OptionsFlow):
    """Handle options flow for DeepSeek Usage."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
