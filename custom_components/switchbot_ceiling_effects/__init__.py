"""SwitchBot Ceiling Effects: effects, speed and brightness for SwitchBot lamps."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant  # noqa: TC002
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Effect, Lamp, SwitchBotAccount, SwitchBotApiError, SwitchBotAuthError
from .const import CONF_DEVICE_TYPE, CONF_GROUP_ID
from .models import MODELS

PLATFORMS = [Platform.LIGHT, Platform.NUMBER, Platform.SELECT]


@dataclass
class LampData:
    """Shared state of one lamp (one config entry)."""

    lamp: Lamp
    effects: dict[str, Effect]
    speed: int


type CeilingEffectsConfigEntry = ConfigEntry[LampData]


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

    entry.runtime_data = LampData(
        lamp, {e.name: e for e in effects}, model.default_speed
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CeilingEffectsConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
