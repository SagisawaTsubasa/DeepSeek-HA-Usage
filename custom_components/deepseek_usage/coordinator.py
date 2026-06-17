"""DataUpdateCoordinator for DeepSeek Usage."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class DeepSeekCoordinator(DataUpdateCoordinator):
    """Coordinator for DeepSeek API balance."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.api_key = entry.data["api_key"]
        self._scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self._scan_interval),
        )

    async def _async_update_data(self):
        """Fetch data from DeepSeek API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.deepseek.com/user/balance",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 401:
                        raise UpdateFailed("API Key 无效或已过期")
                    if response.status != 200:
                        text = await response.text()
                        raise UpdateFailed(f"HTTP {response.status}: {text}")

                    data = await response.json()

                    if not data.get("is_available"):
                        _LOGGER.warning("DeepSeek 余额不可用")

                    balance_info = data.get("balance_infos", [{}])[0]

                    return {
                        "is_available": data.get("is_available", False),
                        "currency": balance_info.get("currency", "CNY"),
                        "total_balance": float(balance_info.get("total_balance", 0)),
                        "granted_balance": float(balance_info.get("granted_balance", 0)),
                        "topped_up_balance": float(balance_info.get("topped_up_balance", 0)),
                    }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"连接失败: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"更新失败: {err}") from err
