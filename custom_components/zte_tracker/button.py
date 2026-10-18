"""Button platform for ZTE Tracker router actions."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZteDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the ZTE action buttons for a config entry."""
    coordinator: ZteDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [ZteRefreshButton(coordinator, entry), ZteRebootButton(coordinator, entry)]
    )


class ZteBaseButton(CoordinatorEntity, ButtonEntity):
    """Base class for router action buttons."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        host = getattr(coordinator.client, "host", "unknown")
        self._attr_should_poll = False
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or f"ZTE Router {host}",
            manufacturer="ZTE",
            model=getattr(coordinator.client, "model", "unknown"),
        )


class ZteRefreshButton(ZteBaseButton):
    """Button entity to trigger an immediate refresh via the coordinator."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator, entry)
        self._attr_name = "Refresh"
        self._attr_unique_id = f"{entry.entry_id}_refresh"
        self._attr_icon = "mdi:refresh"

    @property
    def available(self) -> bool:
        """Allow manual refresh whenever scanning is not paused."""
        return not getattr(self.coordinator, "paused", False)

    async def async_press(self) -> None:  # type: ignore[override]
        """Handle the button press to refresh router data immediately."""
        host = getattr(self.coordinator.client, "host", "unknown")
        _LOGGER.info("Refresh requested via button for host: %s", host)
        try:
            await self.coordinator.async_request_refresh()
        except Exception as exc:  # pragma: no cover - defensive logging
            raise HomeAssistantError(
                f"Exception while refreshing router {host}: {exc}"
            ) from exc


class ZteRebootButton(ZteBaseButton):
    """Button entity to trigger a router reboot via the coordinator."""

    def __init__(self, coordinator: ZteDataCoordinator, entry: ConfigEntry) -> None:
        """Initialize the reboot button."""
        super().__init__(coordinator, entry)
        self._attr_name = "Reboot"
        self._attr_unique_id = f"{entry.entry_id}_reboot"
        self._attr_icon = "mdi:restart"

    @property
    def available(self) -> bool:
        """Disable the reboot button whenever the router is not connected."""
        router_info = (self.coordinator.data or {}).get("router_info", {})
        value = router_info.get("router_connected")
        if isinstance(value, bool):
            return value
        return bool(getattr(self.coordinator, "last_update_success", True))

    async def async_press(self) -> None:  # type: ignore[override]
        """Handle the button press to reboot the router."""
        host = getattr(self.coordinator.client, "host", "unknown")
        _LOGGER.info("Reboot requested via button for host: %s", host)
        try:
            success = await self.coordinator.async_reboot_router(self._context)
            if not success:
                raise HomeAssistantError(
                    f"Router reboot failed for host: {host}"
                )
        except HomeAssistantError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            raise HomeAssistantError(
                f"Exception while rebooting router {host}: {exc}"
            ) from exc