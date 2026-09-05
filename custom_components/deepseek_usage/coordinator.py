"""DataUpdateCoordinator for DeepSeek Usage."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import BALANCE_API_URL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

HISTORY_RETENTION_DAYS = 8

# Throttle disk writes: save on change, or at least every N polls so merged
# (unchanged) snapshots still get their merged timestamp persisted.
_SAVE_EVERY_N_POLLS = 10


class DeepSeekCoordinator(DataUpdateCoordinator):
    """Coordinator for DeepSeek API balance with historical tracking & recharge support."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.api_key = entry.data["api_key"]
        self._scan_interval = int(entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL))
        self.store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_history")
        self.history: list[dict[str, Any]] = []
        self.recharges: list[dict[str, Any]] = []
        self._polls_since_save = 0
        # Snapshots closer together than this are merged. Derived from the
        # poll interval so a manual refresh right after a poll is not lost.
        self._dedup_window = max(5, min(60, self._scan_interval // 2))

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
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
        """Trim balance history beyond retention.

        Recharges are intentionally never pruned: the 累计充值 sensor is the
        sum of ALL recorded recharges, so trimming them would make the total
        shrink over time — silent, unrecoverable data loss.
        """
        cutoff = time.time() - (HISTORY_RETENTION_DAYS * 86400)
        before = len(self.history)
        self.history = [h for h in self.history if h.get("ts", 0) > cutoff]
        if before != len(self.history):
            _LOGGER.debug(
                "Cleaned history: %d->%d (recharges kept: %d)",
                before, len(self.history), len(self.recharges),
            )

    def _append_history(self, ts: float, balance: float) -> bool:
        """Append a new balance snapshot; return True when history changed."""
        if self.history:
            last = self.history[-1]
            if abs(last["ts"] - ts) < self._dedup_window:
                changed = last["balance"] != balance
                last["ts"] = ts
                last["balance"] = balance
                return changed
        self.history.append({"ts": ts, "balance": balance})
        return True

    def _compute_window(self, start_ts: float, end_ts: float) -> float | None:
        """Consumption within [start_ts, end_ts]; None when data is insufficient.

        The baseline is the last snapshot at or before the window start — not
        the first snapshot inside the window — so consumption that happened
        around a window boundary (e.g. midnight) is attributed to the right
        window instead of vanishing from both.
        """
        history = self.history
        if not history:
            return None

        start_snap = None
        for snap in history:
            if snap["ts"] <= start_ts:
                start_snap = snap
            else:
                break
        if start_snap is None:
            # Nothing before the window: use the first snapshot inside the
            # window as the baseline (consumption before it is unknown).
            for snap in history:
                if snap["ts"] <= end_ts:
                    start_snap = snap
                    break
            if start_snap is None:
                return None

        end_snap = None
        for snap in history:
            if snap["ts"] <= end_ts:
                end_snap = snap
            else:
                break

        if end_snap is None or end_snap is start_snap:
            # No snapshot inside the window beyond the baseline: unknown
            # rather than a misleading 0.
            return None

        recharge = sum(
            r["amount"] for r in self.recharges if start_ts < r["ts"] <= end_ts
        )
        return max(0.0, round(start_snap["balance"] - end_snap["balance"] + recharge, 2))

    async def async_record_recharge(self, amount: float) -> None:
        """Record a manual recharge."""
        if amount <= 0:
            raise ValueError("充值金额必须大于 0")
        self.recharges.append({"ts": time.time(), "amount": round(amount, 2)})
        self._cleanup_history()
        await self.store.async_save({"history": self.history, "recharges": self.recharges})
        self._polls_since_save = 0
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

        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                BALANCE_API_URL,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 401:
                    # Propagate as auth failure so HA starts the reauth flow
                    # instead of silently retrying forever.
                    raise ConfigEntryAuthFailed("API Key 无效或已过期")
                if response.status != 200:
                    text = await response.text()
                    raise UpdateFailed(f"HTTP {response.status}: {text}")
                try:
                    data = await response.json()
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise UpdateFailed(f"响应解析失败: {err}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"连接失败: {err}") from err

        if not data.get("is_available"):
            _LOGGER.warning("DeepSeek 余额接口报告不可用")

        # The default of dict.get only applies when the key is MISSING — an
        # empty list from the API must be handled explicitly (H2).
        balance_infos = data.get("balance_infos") or [{}]
        balance_info = balance_infos[0] if balance_infos else {}

        def _num(key: str) -> float:
            try:
                return float(balance_info.get(key) or 0)
            except (TypeError, ValueError):
                return 0.0

        current_total = _num("total_balance")
        now = time.time()

        changed = self._append_history(now, current_total)
        self._cleanup_history()

        self._polls_since_save += 1
        if changed or self._polls_since_save >= _SAVE_EVERY_N_POLLS:
            self._polls_since_save = 0
            try:
                await self.store.async_save(
                    {"history": self.history, "recharges": self.recharges}
                )
            except Exception as err:
                _LOGGER.warning("Failed to save history: %s", err)

        # Calendar-day boundaries via dt_util (DST-safe), not fixed 86400s.
        local_now = dt_util.now()
        today_start = dt_util.start_of_local_day(local_now).timestamp()
        yesterday_start = (
            dt_util.start_of_local_day(local_now) - timedelta(days=1)
        ).timestamp()
        week_start = (
            dt_util.start_of_local_day(local_now) - timedelta(days=local_now.weekday())
        ).timestamp()

        if len(self.history) >= 2:
            prev = self.history[-2]
            cycle_recharge = sum(
                r["amount"] for r in self.recharges if prev["ts"] <= r["ts"] <= now
            )
            cycle_consumed = max(
                0, round(prev["balance"] - current_total + cycle_recharge, 2)
            )
            prev_iso = dt_util.utc_from_timestamp(prev["ts"]).isoformat()
        else:
            cycle_consumed = 0.0
            prev_iso = None

        def _iso(ts: float) -> str:
            return dt_util.utc_from_timestamp(ts).isoformat()

        return {
            "is_available": bool(data.get("is_available", False)),
            "currency": balance_info.get("currency", "CNY") or "CNY",
            "total_balance": current_total,
            "granted_balance": _num("granted_balance"),
            "topped_up_balance": _num("topped_up_balance"),
            "consumed": cycle_consumed,
            "total_recharge": round(sum(r["amount"] for r in self.recharges), 2),
            "consumed_reset": prev_iso,
            "consumed_30m": self._compute_window(now - 1800, now),
            "consumed_3h": self._compute_window(now - 10800, now),
            "consumed_today": self._compute_window(today_start, now),
            "consumed_yesterday": self._compute_window(yesterday_start, today_start),
            "consumed_week": self._compute_window(week_start, now),
            "consumed_today_reset": _iso(today_start),
            "consumed_yesterday_reset": _iso(yesterday_start),
            "consumed_week_reset": _iso(week_start),
        }
