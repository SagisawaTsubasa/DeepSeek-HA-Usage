"""The DeepSeek Usage integration."""
from __future__ import annotations

import hashlib
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SERVICE_RECORD_RECHARGE
from .coordinator import DeepSeekCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

CONFIG_VERSION = 2

SERVICE_SCHEMA = vol.Schema({
    vol.Required("amount"): cv.positive_float,
    vol.Optional("entry_id"): cv.string,
})


def _unique_id_for(api_key: str) -> str:
    """Derive a stable unique id from the API key (multi-account friendly)."""
    return "deepseek_" + hashlib.sha1(api_key.encode()).hexdigest()[:12]


def _async_get_coordinator(
    hass: HomeAssistant, entry_id: str | None
) -> DeepSeekCoordinator | None:
    """Resolve which coordinator a service call targets."""
    entries = hass.data.get(DOMAIN, {})
    if entry_id:
        candidate = entries.get(entry_id)
        return candidate if isinstance(candidate, DeepSeekCoordinator) else None
    coordinators = [
        value for value in entries.values() if isinstance(value, DeepSeekCoordinator)
    ]
    if len(coordinators) == 1:
        return coordinators[0]
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DeepSeek Usage from a config entry."""
    coordinator = DeepSeekCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    if not hass.services.has_service(DOMAIN, SERVICE_RECORD_RECHARGE):

        async def handle_record_recharge(call: ServiceCall) -> None:
            """Handle the record_recharge service call.

            The target coordinator is resolved per call, so the service keeps
            working with multiple accounts and after entry removals.
            """
            coordinator = _async_get_coordinator(hass, call.data.get("entry_id"))
            if coordinator is None:
                raise HomeAssistantError(
                    "record_recharge: 无法确定目标账户，请在多账户配置时提供 entry_id"
                )
            await coordinator.async_record_recharge(call.data["amount"])

        hass.services.async_register(
            DOMAIN, SERVICE_RECORD_RECHARGE, handle_record_recharge, schema=SERVICE_SCHEMA
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        removed = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if removed is None:
            _LOGGER.debug("Unload of %s: no coordinator was registered", entry.entry_id)
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_RECORD_RECHARGE)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry so option changes take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate to the key-derived unique id (v2) so multiple accounts work.

    The entity registry references entities by config entry id, not by the
    entry unique_id, so existing entities keep their ids and states.
    """
    if entry.version > CONFIG_VERSION:
        return False
    if entry.version < CONFIG_VERSION:
        if entry.unique_id == "deepseek_usage_unique":
            api_key = entry.data.get("api_key", "")
            hass.config_entries.async_update_entry(
                entry, unique_id=_unique_id_for(api_key)
            )
        hass.config_entries.async_update_entry(entry, version=CONFIG_VERSION)
        _LOGGER.info("Migrated config entry %s to version %d", entry.title, CONFIG_VERSION)
    return True
