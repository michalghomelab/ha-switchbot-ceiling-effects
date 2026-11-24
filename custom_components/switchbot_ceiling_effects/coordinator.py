"""Polls the lamp state the cloud keeps."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LampState, SwitchBotApiError, SwitchBotAuthError

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .api import Effect, Lamp

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)
# How long to wait after a command before reading the state back, so the lamp
# has reported the change to the cloud.
SETTLE_SECONDS = 3


class CeilingCoordinator(DataUpdateCoordinator[LampState]):
    """Keeps the lamp state, the effect list and the speed in one place."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        lamp: Lamp,
        effects: list[Effect],
    ) -> None:
        """Set up polling for one lamp."""
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            update_interval=SCAN_INTERVAL,
            config_entry=entry,
        )
        self.lamp = lamp
        self.effects = {effect.name: effect for effect in effects}
        # The lamp does not report the effect speed or which effect is running,
        # so both are what this integration last sent.
        self.speed = lamp.model.default_speed
        self.effect_name: str | None = None

    async def _async_update_data(self) -> LampState:
        """Read the state the lamp reports to the cloud."""
        try:
            return await self.lamp.get_state()
        except SwitchBotAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SwitchBotApiError as err:
            raise UpdateFailed(str(err)) from err

    async def async_refresh_soon(self) -> None:
        """Read the state back once the lamp has reported a change."""
        self.hass.loop.call_later(
            SETTLE_SECONDS, lambda: self.hass.async_create_task(self.async_refresh())
        )
