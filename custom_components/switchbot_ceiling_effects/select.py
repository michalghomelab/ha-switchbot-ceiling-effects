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
    """
    Starts an effect on the color light, or turns the color light off.

    The lamp reports whether an effect is running, but not which one, so the
    name is the one this integration last sent.
    """

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the selector with the effects saved in the account."""
        super().__init__(entry, "effect")
        self._attr_options = [EFFECT_OFF, *self.coordinator.effects]

    async def async_added_to_hass(self) -> None:
        """Remember the effect chosen before the last restart."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state in self.coordinator.effects:
            self.coordinator.effect_name = state.state

    @property
    def current_option(self) -> str | None:
        """
        The running effect, or `off` when no effect is running.

        An effect started elsewhere leaves this unknown: the lamp reports that
        an effect runs, but not which one.
        """
        data = self.coordinator.data
        if data.color_on is False or data.effect_running is False:
            return EFFECT_OFF
        return self.coordinator.effect_name

    async def async_select_option(self, option: str) -> None:
        """Start the effect at the current speed, or turn the color light off."""
        if option == EFFECT_OFF:
            await self._run("turn off", self._lamp.turn_off_color_light())
            self.coordinator.effect_name = None
        else:
            # Only the color light is touched; the main white light stays as it is.
            effect = self.coordinator.effects[option]
            await self._run(
                "effect", self._lamp.start_effect(effect, self.coordinator.speed)
            )
            self.coordinator.effect_name = option
        self.async_write_ha_state()
