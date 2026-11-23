"""Effect selector."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import EFFECTS
from .entity import CeilingEffectsEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import CeilingEffectsConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: CeilingEffectsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the effect selector."""
    async_add_entities([EffectSelect(entry)])


class EffectSelect(CeilingEffectsEntity, SelectEntity, RestoreEntity):
    """Starts a preset effect on the color light."""

    _attr_options = EFFECTS

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the selector."""
        super().__init__(entry, "effect")

    async def async_added_to_hass(self) -> None:
        """Restore the last chosen effect."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) and state.state in EFFECTS:
            self._attr_current_option = state.state

    async def async_select_option(self, option: str) -> None:
        """Start the effect."""
        await self._send("setLightEffect", {"effectId": EFFECTS.index(option)})
        self._attr_current_option = option
        self.async_write_ha_state()
