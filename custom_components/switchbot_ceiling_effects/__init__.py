"""SwitchBot Ceiling Effects for the RGBICWW Ceiling Light."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant  # noqa: TC002
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SwitchBotApi
from .const import CONF_SECRET

PLATFORMS = [Platform.NUMBER, Platform.SELECT]

type CeilingEffectsConfigEntry = ConfigEntry[SwitchBotApi]


async def async_setup_entry(
    hass: HomeAssistant, entry: CeilingEffectsConfigEntry
) -> bool:
    """Set up one lamp from a config entry."""
    entry.runtime_data = SwitchBotApi(
        async_get_clientsession(hass), entry.data[CONF_TOKEN], entry.data[CONF_SECRET]
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: CeilingEffectsConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
