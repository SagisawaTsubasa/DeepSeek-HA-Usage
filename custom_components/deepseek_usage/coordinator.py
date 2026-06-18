"""DataUpdateCoordinator for DeepSeek Usage."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

HISTORY_RETENTION_DAYS = 8


class DeepSeekCoordinator(DataUpdateCoordinator):
    """Coordinator for DeepSeek API balance with historical tracking & recharge support."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.api_key = entry.data["api_key"]
        self._scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        self.store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_history")
        self.history: list[dict[str, Any]] = []
        self.recharges: list[dict[str, Any]] = []

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self._scan_interval),
        )

    async def _async_load_history(self) -> None:
        """Load persisted balance history and recharges."""
        try:
            stored = await self.store.async_load()
            if stored:
                if isinstance(stored.get("history"), list):
                    self.history = stored["history"]
                if isinstance(stored.get("recharges"), list):
                    self.recharges = stored["recharges"]
                _LOGGER.debug(
                    "Loaded %d history entries, %d recharges",
                    len(self.history), len(self.recharges),
                )
        except Exception as err:
            _LOGGER.warning("Failed to load history: %s", err)
            self.history = []
            self.recharges = []

    def _cleanup_history(self) -> None:
        """Remove old entries beyond retention."""
        cutoff = time.time() - (HISTORY_RETENTION_DAYS * 86400)
        before_h = len(self.history)
        before_r = len(self.recharges)
        self.history = [h for h in self.history if h.get("ts", 0) > cutoff]
        self.recharges = [r for r in self.recharges if r.get("ts", 0) > cutoff]
        _LOGGER.debug(
            "Cleaned history: %d->%d, recharges: %d->%d",
            before_h, len(self.history), before_r, len(self.recharges),
        )

    def _append_history(self, ts: float, balance: float) -> None:
        """Append a new balance snapshot."""
        if self.history:
            last = self.history[-1]
            if abs(last["ts"] - ts) < 60:
                last["ts"] = ts
                last["balance"] = balance
                return
        self.history.append({"ts": ts, "balance": balance})

    def _find_window_start_balance(self, target_ts: float) -> float | None:
        """Find the oldest balance entry within the window."""
        valid = [h["balance"] for h in self.history if h["ts"] >= target_ts]
        if not valid:
            return None
        return valid[0]

    def _window_recharge_total(self, start_ts: float) -> float:
        """Sum recharges within [start_ts, now]."""
        now = time.time()
        return sum(
            r["amount"] for r in self.recharges if start_ts <= r["ts"] <= now
        )

    def _calc_consumed(self, start_balance: float | None, current: float, recharge_in_window: float = 0.0) -> float | None:
        """Calculate consumption, accounting for recharges."""
        if start_balance is None:
            return None
        # 实际消耗 = 起始余额 - 当前余额 + 窗口内充值
        # 因为充值会让余额上升，需要加回来
        raw = start_balance - current + recharge_in_window
        return max(0.0, round(raw, 2))

    def _compute_windows(self, current_balance: float) -> dict[str, float | None]:
        """Compute consumption for various time windows."""
        now = time.time()
        now_dt = datetime.fromtimestamp(now)

        today_start = datetime(now_dt.year, now_dt.month, now_dt.day).timestamp()
        yesterday_start = today_start - 86400
        weekday = now_dt.weekday()
        week_start = today_start - weekday * 86400

        windows = {
            "consumed_30m": self._calc_consumed(
                self._find_window_start_balance(now - 1800),
                current_balance,
                self._window_recharge_total(now - 1800),
            ),
            "consumed_3h": self._calc_consumed(
                self._find_window_start_balance(now - 10800),
                current_balance,
                self._window_recharge_total(now - 10800),
            ),
            "consumed_today": self._calc_consumed(
                self._find_window_start_balance(today_start),
                current_balance,
                self._window_recharge_total(today_start),
            ),
            "consumed_yesterday": self._calc_consumed(
                self._find_window_start_balance(yesterday_start),
                current_balance,
                self._window_recharge_total(yesterday_start),
            ),
            "consumed_week": self._calc_consumed(
                self._find_window_start_balance(week_start),
                current_balance,
                self._window_recharge_total(week_start),
            ),
        }
        return windows

    async def async_record_recharge(self, amount: float) -> None:
        """Record a manual recharge."""
        if amount <= 0:
            raise ValueError("充值金额必须大于 0")
        self.recharges.append({"ts": time.time(), "amount": round(amount, 2)})
        self._cleanup_history()
        await self.store.async_save({"history": self.history, "recharges": self.recharges})
        _LOGGER.info("Recorded recharge: %.2f CNY", amount)
        await self.async_request_refresh()

    async def _async_update_data(self):
        """Fetch data from DeepSeek API and compute windows."""
        if not self.history:
            await self._async_load_history()

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
                    current_total = float(balance_info.get("total_balance", 0))
                    now_ts = time.time()

                    self._append_history(now_ts, current_total)
                    self._cleanup_history()
                    try:
                        await self.store.async_save({"history": self.history, "recharges": self.recharges})
                    except Exception as err:
                        _LOGGER.warning("Failed to save history: %s", err)

                    windows = self._compute_windows(current_total)

                    if len(self.history) >= 2:
                        prev = self.history[-2]["balance"]
                        # 最近周期消耗也考虑充值（从上次刷新到现在）
                        cycle_recharge = self._window_recharge_total(self.history[-2]["ts"])
                        cycle_consumed = max(0, round(prev - current_total + cycle_recharge, 2))
                    else:
                        cycle_consumed = 0.0

                    total_recharge = sum(r["amount"] for r in self.recharges)

                    return {
                        "is_available": data.get("is_available", False),
                        "currency": balance_info.get("currency", "CNY"),
                        "total_balance": current_total,
                        "granted_balance": float(balance_info.get("granted_balance", 0)),
                        "topped_up_balance": float(balance_info.get("topped_up_balance", 0)),
                        "consumed": cycle_consumed,
                        "total_recharge": round(total_recharge, 2),
                        **windows,
                    }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"连接失败: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"更新失败: {err}") from err
