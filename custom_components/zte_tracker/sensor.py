"""Sensor platform for ZTE Tracker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as ha_dt

from .const import DOMAIN, ICON
from .coordinator import ZteDataCoordinator


@dataclass(frozen=True)
class ZteOpticalSensorDescription:
    key: str
    name: str
    unique_id_suffix: str
    icon: str | None = None
    native_unit_of_measurement: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None


OPTICAL_SENSORS: tuple[ZteOpticalSensorDescription, ...] = (
    ZteOpticalSensorDescription(
        key="PON_onu_state",
        name="ONU State",
        unique_id_suffix="pon_onu_state",
        icon="mdi:fiber-optic",
    ),
    ZteOpticalSensorDescription(
        key="PON_rx_power_dbm",
        name="Optical Module Input Power",
        unique_id_suffix="pon_rx_power",
        icon="mdi:download-network-outline",
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZteOpticalSensorDescription(
        key="PON_tx_power_dbm",
        name="Optical Module Output Power",
        unique_id_suffix="pon_tx_power",
        icon="mdi:upload-network-outline",
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZteOpticalSensorDescription(
        key="PON_supply_voltage_mv",
        name="Optical Module Supply Voltage",
        unique_id_suffix="pon_supply_voltage",
        icon="mdi:sine-wave",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZteOpticalSensorDescription(
        key="PON_bias_current_ma",
        name="Optical Transmitter Bias Current",
        unique_id_suffix="pon_bias_current",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZteOpticalSensorDescription(
        key="PON_temperature_c",
        name="Operating Temperature of the Optical Module",
        unique_id_suffix="pon_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ZTE sensor from config entry."""
    coordinator: ZteDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            ZteRouterSensor(coordinator, entry),
            ZteDeviceCountSensor(coordinator, entry),
            *[
                ZteOpticalMetricSensor(coordinator, entry, description)
                for description in OPTICAL_SENSORS
                if coordinator.client.paths.get("tag_pon_optical_data")
            ],
        ]
    )


class ZteBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for ZTE sensors."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        router_info = (coordinator.data or {}).get("router_info", {}) or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"ZTE Router {coordinator.client.host}",
            manufacturer=router_info.get("ManuFacturer", "ZTE"),
            model=router_info.get("ModelName") or coordinator.client.model,
            sw_version=router_info.get("SoftwareVer"),
            hw_version=router_info.get("HardwareVer"),
            # The scheme is per profile and the user can override it, so the
            # link is taken from the client rather than assumed. It was
            # hardcoded to https, which is a dead link on an http only unit.
            configuration_url=getattr(coordinator.client, "base_url", None),
        )


class ZteRouterSensor(ZteBaseSensor):
    """Sensor representing the router status."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        """Initialize the router sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = f"ZTE Router {coordinator.client.host}"
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_icon = ICON

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        data = self.coordinator.data or {}
        router_info = data.get("router_info", {})
        status = str(router_info.get("status", "unknown"))
        return status.replace("_", " ").title()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        data = self.coordinator.data or {}
        router_info = data.get("router_info", {})
        # Return a copy to avoid mutating shared coordinator.data
        interval = self.coordinator.update_interval
        return {
            **router_info,
            "last_update": ha_dt.now().isoformat(),
            "poll_interval": int(interval.total_seconds()) if interval else None,
        }


class ZteDeviceCountSensor(ZteBaseSensor):
    """Sensor for the number of connected devices."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        """Initialize the device count sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = f"ZTE Router {coordinator.client.host} Devices"
        self._attr_unique_id = f"{entry.entry_id}_device_count"
        self._attr_icon = "mdi:devices"
        self._attr_native_unit_of_measurement = "devices"

    @property
    def native_value(self) -> int:
        """Return the number of connected devices."""
        data = self.coordinator.data or {}
        devices = data.get("devices", {})
        return len([d for d in devices.values() if d.get("active")])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes, including the list of detected devices."""
        data = self.coordinator.data or {}
        devices = data.get("devices", {})
        device_list = [
            f"{mac}({device.get('name', 'Unknown')}-{device.get('ip', '')})"
            for mac, device in devices.items()
        ]
        return {
            "devices": device_list,
            "num_devices": len([d for d in devices.values() if d.get("active")]),
        }


class ZteOpticalMetricSensor(ZteBaseSensor):
    """Diagnostic sensor backed by router optical data."""

    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: ZteDataCoordinator,
        entry: ConfigEntry,
        description: ZteOpticalSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_name = (
            f"ZTE Router {coordinator.client.host} {description.name}"
        )
        self._attr_unique_id = f"{entry.entry_id}_{description.unique_id_suffix}"
        self._attr_icon = description.icon
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class

    @property
    def available(self) -> bool:
        """Return whether the entity has a current value to expose."""
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> Any:
        """Return the current optical metric."""
        router_info = (self.coordinator.data or {}).get("router_info", {})
        return router_info.get(self.entity_description.key)
