"""Sensor platform for DeepSeek Usage."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeepSeekCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the DeepSeek sensors."""
    coordinator: DeepSeekCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, config_entry.entry_id)},
        name="DeepSeek Usage",
        manufacturer="DeepSeek",
        model="API Balance",
        entry_type=DeviceEntryType.SERVICE,
    )

    sensors = [
        DeepSeekBalanceSensor(coordinator, "total_balance", device_info),
        DeepSeekBalanceSensor(coordinator, "granted_balance", device_info),
        DeepSeekBalanceSensor(coordinator, "topped_up_balance", device_info),
        DeepSeekAvailabilitySensor(coordinator, device_info),
        DeepSeekConsumedSensor(coordinator, "consumed", device_info),
        DeepSeekConsumedSensor(coordinator, "consumed_30m", device_info),
        DeepSeekConsumedSensor(coordinator, "consumed_3h", device_info),
        DeepSeekConsumedSensor(coordinator, "consumed_today", device_info),
        DeepSeekConsumedSensor(coordinator, "consumed_yesterday", device_info),
        DeepSeekConsumedSensor(coordinator, "consumed_week", device_info),
        DeepSeekRechargeSensor(coordinator, device_info),
    ]

    async_add_entities(sensors)


class DeepSeekBalanceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a DeepSeek balance sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "CNY"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(
        self,
        coordinator: DeepSeekCoordinator,
        key: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"deepseek_{key}_{coordinator.entry.entry_id}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._key)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "currency": self.coordinator.data.get("currency"),
        }


class DeepSeekAvailabilitySensor(CoordinatorEntity, SensorEntity):
    """Representation of DeepSeek availability."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_icon = "mdi:cloud-check"

    def __init__(self, coordinator: DeepSeekCoordinator, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_translation_key = "is_available"
        self._attr_options = ["on", "off"]
        self._attr_unique_id = f"deepseek_is_available_{coordinator.entry.entry_id}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return "on" if self.coordinator.data.get("is_available") else "off"


class DeepSeekConsumedSensor(CoordinatorEntity, SensorEntity):
    """Representation of consumed amount over a time window."""

    _attr_has_entity_name = True
    # Period windows (today/yesterday/week/cycle) reset — declare TOTAL and
    # expose last_reset so long-term statistics interpret them correctly;
    # rolling windows (30m/3h) keep MEASUREMENT semantics.
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "CNY"
    _attr_device_class = SensorDeviceClass.MONETARY

    # Keys whose value resets at a window boundary.
    TOTAL_KEYS = frozenset({"consumed", "consumed_today", "consumed_yesterday", "consumed_week"})

    def __init__(
        self,
        coordinator: DeepSeekCoordinator,
        key: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"deepseek_{key}_{coordinator.entry.entry_id}"
        self._attr_device_info = device_info
        if key in self.TOTAL_KEYS:
            self._attr_state_class = SensorStateClass.TOTAL
        else:
            # MONETARY only allows TOTAL/TOTAL_INCREASING state classes; the
            # rolling windows go down over time so they keep MEASUREMENT and
            # drop the device class instead (kills the recorder warning).
            self._attr_device_class = None

    @property
    def native_value(self):
        """Return the consumed amount (None = no data yet, keeps stats clean)."""
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:
        """Return if sensor has data."""
        return self.coordinator.data.get(self._key) is not None

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        return {
            "currency": self.coordinator.data.get("currency"),
            "last_reset": self.coordinator.data.get(f"{self._key}_reset"),
        }


class DeepSeekRechargeSensor(CoordinatorEntity, SensorEntity):
    """Representation of total recorded recharge amount."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "CNY"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator: DeepSeekCoordinator, device_info: DeviceInfo) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_translation_key = "total_recharge"
        self._attr_unique_id = f"deepseek_total_recharge_{coordinator.entry.entry_id}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """Return total recorded recharge amount."""
        return self.coordinator.data.get("total_recharge", 0)

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        return {
            "currency": self.coordinator.data.get("currency"),
        }
