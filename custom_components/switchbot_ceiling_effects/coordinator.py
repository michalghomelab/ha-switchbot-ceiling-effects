"""Keeps the lamp state: from its Bluetooth broadcasts, or from the cloud."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LampState, SwitchBotApiError, SwitchBotAuthError

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .api import Effect, Lamp
    from .ble import BleBackend

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)
# The lamp broadcasts every few seconds. While broadcasts keep arriving, the
# cloud is not asked at all.
BROADCAST_TIMEOUT = 120
# How long to wait after a command before reading the state back from the
# cloud, so the lamp has reported the change.
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
        # The lamp reports neither the effect speed nor which effect is
        # running, so both are what this integration last sent.
        self.speed = lamp.model.default_speed
        self.effect_name: str | None = None
        self._last_broadcast = 0.0

    @property
    def broadcasts_arriving(self) -> bool:
        """Whether the lamp's own broadcasts are keeping the state current."""
        return time.monotonic() - self._last_broadcast < BROADCAST_TIMEOUT

    def listen_to_broadcasts(self, ble: BleBackend) -> Callable[[], None]:
        """Follow the lamp's Bluetooth broadcasts; returns an unsubscribe."""
        props = self.lamp.model.properties
        if props is None:
            return lambda: None

        def _on_state(state: LampState) -> None:
            self._last_broadcast = time.monotonic()
            self.async_set_updated_data(state)

        return ble.listen(props, _on_state)

    async def _async_update_data(self) -> LampState:
        """Read the state from the cloud, unless broadcasts already have it."""
        if self.broadcasts_arriving and self.data is not None:
            return self.data
        try:
            return await self.lamp.get_state()
        except SwitchBotAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SwitchBotApiError as err:
            raise UpdateFailed(str(err)) from err

    async def async_refresh_soon(self) -> None:
        """
        Read the state back once the lamp has reported a change.

        Broadcasts arrive on their own, so this only matters for the cloud.
        """
        if self.broadcasts_arriving:
            return
        self.hass.loop.call_later(
            SETTLE_SECONDS, lambda: self.hass.async_create_task(self.async_refresh())
        )
