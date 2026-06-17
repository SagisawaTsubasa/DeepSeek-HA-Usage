"""Sensor platform for DeepSeek Usage."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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

    sensors = [
        DeepSeekBalanceSensor(coordinator, "total_balance", "总余额"),
        DeepSeekBalanceSensor(coordinator, "granted_balance", "赠送余额"),
        DeepSeekBalanceSensor(coordinator, "topped_up_balance", "充值余额"),
        DeepSeekAvailabilitySensor(coordinator),
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
        name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"deepseek_{key}"

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

    def __init__(self, coordinator: DeepSeekCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "余额可用"
        self._attr_unique_id = "deepseek_is_available"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return "on" if self.coordinator.data.get("is_available") else "off"
