"""Effect selector."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import EFFECT_OFF
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
    """Starts an effect on the color light, or turns the color light off."""

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the selector with the effects saved in the account."""
        super().__init__(entry, "effect")
        self._attr_options = [EFFECT_OFF, *self._data.effects]

    async def async_added_to_hass(self) -> None:
        """Restore the last chosen effect."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) and state.state in self.options:
            self._attr_current_option = state.state

    async def async_select_option(self, option: str) -> None:
        """Start the effect at the current speed, or turn the color light off."""
        if option == EFFECT_OFF:
            await self._run("turn off", self._lamp.turn_off_color_light())
        else:
            # Only the color light is touched; the main white light stays with Matter.
            effect = self._data.effects[option]
            await self._run("effect", self._lamp.start_effect(effect, self._data.speed))
        self._attr_current_option = option
        self.async_write_ha_state()
