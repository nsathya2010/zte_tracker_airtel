"""Binary sensor platform for ZTE Tracker."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZteDataCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ZTE binary sensors from a config entry."""
    coordinator: ZteDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[CoordinatorEntity] = [
        ZteRouterConnectedBinarySensor(coordinator, entry),
        ZteInternetConnectedBinarySensor(coordinator, entry),
    ]
    if coordinator.client.paths.get("tag_pon_optical_data"):
        entities.extend(
            [
                ZteFiberConnectedBinarySensor(coordinator, entry),
                ZteLosBinarySensor(coordinator, entry),
            ]
        )

    async_add_entities(entities)


class ZteBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base class for ZTE binary sensors."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        router_info = (coordinator.data or {}).get("router_info", {}) or {}
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or f"ZTE Router {coordinator.client.host}",
            manufacturer=router_info.get("ManuFacturer", "ZTE"),
            model=router_info.get("ModelName") or coordinator.client.model,
            sw_version=router_info.get("SoftwareVer"),
            hw_version=router_info.get("HardwareVer"),
            configuration_url=getattr(coordinator.client, "base_url", None),
        )


class ZteRouterConnectedBinarySensor(ZteBaseBinarySensor):
    """Router reachability derived from coordinator success."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Router"
        self._attr_unique_id = f"{entry.entry_id}_router_connected"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self) -> bool:
        """Return whether the router itself is reachable."""
        router_info = (self.coordinator.data or {}).get("router_info", {})
        value = router_info.get("router_connected")
        return bool(value)


class ZteInternetConnectedBinarySensor(ZteBaseBinarySensor):
    """Internet reachability based on the router's WAN state."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Internet"
        self._attr_unique_id = f"{entry.entry_id}_internet_connected"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def available(self) -> bool:
        """Return whether internet state is currently known."""
        return self.coordinator.last_update_success and self.is_on is not None

    @property
    def is_on(self) -> bool | None:
        """Return the router-reported internet state."""
        router_info = (self.coordinator.data or {}).get("router_info", {})
        value = router_info.get("internet_connected")
        if isinstance(value, bool):
            return value
        return None


class ZteFiberConnectedBinarySensor(ZteBaseBinarySensor):
    """Fiber status derived from the direct LOS flag."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Fiber"
        self._attr_unique_id = f"{entry.entry_id}_fiber_connected"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def available(self) -> bool:
        """Return whether fiber state is currently known."""
        return self.coordinator.last_update_success and self.is_on is not None

    @property
    def is_on(self) -> bool | None:
        """Return True when LOS is clear and fiber is up."""
        router_info = (self.coordinator.data or {}).get("router_info", {})
        value = router_info.get("fiber_connected")
        if isinstance(value, bool):
            return value
        return None


class ZteLosBinarySensor(ZteBaseBinarySensor):
    """Loss-of-signal alarm derived only from the router's direct LOS flag."""

    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Optical LOS"
        self._attr_unique_id = f"{entry.entry_id}_pon_los"
        self._attr_icon = "mdi:alarm-light-outline"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def available(self) -> bool:
        """Return whether the router currently reports LOS state."""
        return self.coordinator.last_update_success and self.is_on is not None

    @property
    def icon(self) -> str | None:
        """Show a healthy icon when LOS is clear and an alarm when it is active."""
        return "mdi:alarm-light" if self.is_on else "mdi:check-circle-outline"

    @property
    def is_on(self) -> bool | None:
        """Return the direct router LOS flag when available."""
        router_info = (self.coordinator.data or {}).get("router_info", {})
        value = router_info.get("PON_loss_of_signal")
        if isinstance(value, bool):
            return value
        return None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Expose current and previous LOS timing details."""
        router_info = (self.coordinator.data or {}).get("router_info", {})
        return {
            "onu_state": router_info.get("PON_onu_state"),
            "los_since": router_info.get("PON_los_since"),
            "los_duration_seconds": router_info.get("PON_los_duration_seconds"),
            "last_outage_seconds": router_info.get("PON_last_outage_seconds"),
            "last_recovery_at": router_info.get("PON_last_recovery_at"),
        }