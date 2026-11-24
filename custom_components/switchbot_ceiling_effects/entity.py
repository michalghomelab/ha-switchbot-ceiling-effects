"""Base entity shared by all platforms."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SwitchBotApiError
from .const import DOMAIN
from .coordinator import CeilingCoordinator

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from . import CeilingEffectsConfigEntry


class CeilingEffectsEntity(CoordinatorEntity[CeilingCoordinator]):
    """Shares the lamp, its polled state and error handling."""

    _attr_has_entity_name = True

    def __init__(self, entry: CeilingEffectsConfigEntry, key: str) -> None:
        """Set up identifiers shared by all entities of one lamp."""
        super().__init__(entry.runtime_data)
        self._lamp = self.coordinator.lamp
        mac = self._lamp.mac
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=entry.data[CONF_NAME],
            manufacturer="SwitchBot",
            model=self._lamp.model.name,
        )

    async def _run(self, action: str, call: Awaitable[None]) -> None:
        """Send a command, then read the lamp state back."""
        try:
            await call
        except SwitchBotApiError as err:
            msg = f"SwitchBot {action} failed: {err}"
            raise HomeAssistantError(msg) from err
        await self.coordinator.async_refresh_soon()
