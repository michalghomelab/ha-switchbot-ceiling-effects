"""Base entity shared by the select and number platforms."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_DEVICE_ID, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .api import SwitchBotApiError
from .const import DEVICE_TYPE, DOMAIN

if TYPE_CHECKING:
    from . import CeilingEffectsConfigEntry


class CeilingEffectsEntity(Entity):
    """Write-only entity: the API does not report the active effect or speed."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: CeilingEffectsConfigEntry, key: str) -> None:
        """Set up identifiers shared by all entities of one lamp."""
        self._api = entry.runtime_data
        self._device_id: str = entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{self._device_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=entry.data[CONF_NAME],
            manufacturer="SwitchBot",
            model=DEVICE_TYPE,
        )

    async def _send(self, command: str, parameter: Any) -> None:
        try:
            await self._api.send_command(self._device_id, command, parameter)
        except SwitchBotApiError as err:
            msg = f"SwitchBot {command} failed: {err}"
            raise HomeAssistantError(msg) from err
