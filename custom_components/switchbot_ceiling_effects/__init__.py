"""SwitchBot Ceiling Effects: effects, speed and brightness for SwitchBot lamps."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant  # noqa: TC002
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Lamp, SwitchBotAccount, SwitchBotApiError, SwitchBotAuthError
from .ble import BleBackend
from .const import CONF_BLE_KEY, CONF_BLE_KEY_ID, CONF_DEVICE_TYPE, CONF_GROUP_ID
from .coordinator import CeilingCoordinator
from .models import MODELS

if TYPE_CHECKING:
    from .models import LampModel

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.LIGHT, Platform.NUMBER]

type CeilingEffectsConfigEntry = ConfigEntry[CeilingCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: CeilingEffectsConfigEntry
) -> bool:
    """Set up one lamp from a config entry."""
    model = MODELS.get(entry.data[CONF_DEVICE_TYPE])
    if model is None:
        msg = f"unsupported device type {entry.data[CONF_DEVICE_TYPE]}"
        raise ConfigEntryNotReady(msg)

    account = SwitchBotAccount(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    mac = entry.data[CONF_DEVICE_ID]
    key_id, key = await _async_bluetooth_key(hass, entry, account, model, mac)
    ble = (
        BleBackend(hass, model.ble, mac, key_id, key)
        if model.ble is not None and key_id and key
        else None
    )
    lamp = Lamp(account, model, mac, ble)
    try:
        effects = await lamp.get_effects(entry.data[CONF_GROUP_ID])
    except SwitchBotAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SwitchBotApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = CeilingCoordinator(hass, entry, lamp, effects)
    if ble is not None:
        entry.async_on_unload(coordinator.listen_to_broadcasts(ble))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_bluetooth_key(
    hass: HomeAssistant,
    entry: CeilingEffectsConfigEntry,
    account: SwitchBotAccount,
    model: LampModel,
    mac: str,
) -> tuple[str | None, str | None]:
    """
    Return the lamp's Bluetooth key, reading it once if it is missing.

    Lamps added before this integration could use Bluetooth have no key
    stored, so it is fetched here instead of making the user add them again.
    """
    key_id, key = entry.data.get(CONF_BLE_KEY_ID), entry.data.get(CONF_BLE_KEY)
    if model.ble is None or (key_id and key):
        return key_id, key

    try:
        key_id, key = await account.get_ble_key(mac)
    except SwitchBotAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SwitchBotApiError as err:
        _LOGGER.info("No Bluetooth key for %s, using the cloud: %s", entry.title, err)
        return None, None

    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_BLE_KEY_ID: key_id, CONF_BLE_KEY: key},
    )
    _LOGGER.debug("Stored the Bluetooth key for %s", entry.title)
    return key_id, key


async def async_unload_entry(
    hass: HomeAssistant, entry: CeilingEffectsConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
