"""SwitchBot Ceiling Effects: effects, speed and brightness for SwitchBot lamps."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant  # noqa: TC002
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Lamp, SwitchBotAccount, SwitchBotApiError, SwitchBotAuthError
from .const import CONF_DEVICE_TYPE, CONF_GROUP_ID
from .coordinator import CeilingCoordinator
from .models import MODELS

PLATFORMS = [Platform.LIGHT, Platform.NUMBER, Platform.SELECT]

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
    lamp = Lamp(account, model, entry.data[CONF_DEVICE_ID])
    try:
        effects = await lamp.get_effects(entry.data[CONF_GROUP_ID])
    except SwitchBotAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SwitchBotApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = CeilingCoordinator(hass, entry, lamp, effects)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CeilingEffectsConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
