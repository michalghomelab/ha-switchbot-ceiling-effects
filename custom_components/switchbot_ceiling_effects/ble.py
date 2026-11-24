"""
Sends commands to the lamp over Bluetooth, through pySwitchbot.

Home Assistant's Bluetooth stack finds the lamp through any adapter or ESPHome
proxy in range, so this works without the SwitchBot cloud.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components import bluetooth
from homeassistant.core import callback
from switchbot import SwitchbotModel
from switchbot.adv_parser import parse_advertisement_data
from switchbot.devices.light_strip import SwitchbotRgbicwwCeilingLight

from .api import SwitchBotBleError, ble_address, state_from_advertisement

if TYPE_CHECKING:
    from collections.abc import Callable

    from bleak.backends.device import BLEDevice
    from homeassistant.core import HomeAssistant
    from switchbot.devices.device import SwitchbotEncryptedDevice

    from .api import LampState
    from .models import BleProfile, Properties

_LOGGER = logging.getLogger(__name__)

# Lamp classes of pySwitchbot by the model name in the lamp's BLE profile.
DEVICE_CLASSES: dict[str, type[SwitchbotEncryptedDevice]] = {
    "RGBICWW_CEILING_LIGHT": SwitchbotRgbicwwCeilingLight,
}


class BleBackend:
    """Talks to one lamp over Bluetooth, if it is in range."""

    def __init__(
        self,
        hass: HomeAssistant,
        profile: BleProfile,
        mac: str,
        key_id: str,
        encryption_key: str,
    ) -> None:
        """Remember how to reach the lamp; connect only when sending."""
        self._hass = hass
        self._profile = profile
        self._address = ble_address(mac)
        self._key_id = key_id
        self._encryption_key = encryption_key
        self._device_class = DEVICE_CLASSES.get(profile.model)

    def _ble_device(self) -> BLEDevice | None:
        """Return the lamp as an adapter or proxy that can connect to it sees it."""
        return bluetooth.async_ble_device_from_address(
            self._hass, self._address, connectable=True
        )

    @property
    def available(self) -> bool:
        """Whether the lamp is in range right now."""
        return self._device_class is not None and self._ble_device() is not None

    def listen(
        self, props: Properties, on_state: Callable[[LampState], None]
    ) -> Callable[[], None]:
        """Report the lamp state from its broadcasts; returns an unsubscribe."""

        @callback
        def _advertisement(
            service_info: bluetooth.BluetoothServiceInfoBleak,
            change: bluetooth.BluetoothChange,  # noqa: ARG001
        ) -> None:
            parsed = parse_advertisement_data(
                service_info.device,
                service_info.advertisement,
                SwitchbotModel[self._profile.model],
            )
            data = (parsed.data.get("data") if parsed else None) or {}
            if data:
                on_state(state_from_advertisement(data, props))

        return bluetooth.async_register_callback(
            self._hass,
            _advertisement,
            bluetooth.BluetoothCallbackMatcher(address=self._address),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )

    async def send(self, commands: list[str]) -> None:
        """Send hex commands in order; raise so the cloud can take over."""
        device = self._ble_device()
        if device is None or self._device_class is None:
            msg = f"{self._address} is not in range of any Bluetooth adapter"
            raise SwitchBotBleError(msg)

        lamp = self._device_class(
            device,
            self._key_id,
            self._encryption_key,
            model=SwitchbotModel[self._profile.model],
        )
        for command in commands:
            try:
                # pySwitchbot has no public call for a raw command, and the
                # commands differ per lamp, so the lamp class is used for its
                # encrypted transport only.
                result = await lamp._send_command(command)  # noqa: SLF001
            except Exception as err:
                msg = f"sending {command[:10]} failed: {err}"
                raise SwitchBotBleError(msg) from err
            # The lamp answers with a status byte; 1 means it ran the command.
            if not result or result[0] != 1:
                msg = f"the lamp rejected {command[:10]}"
                raise SwitchBotBleError(msg)
        _LOGGER.debug(
            "Sent %d command(s) to %s over Bluetooth", len(commands), self._address
        )
