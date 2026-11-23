"""Color light (effect) brightness."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import PERCENTAGE

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
    """Add the brightness slider."""
    async_add_entities([EffectBrightness(entry)])


class EffectBrightness(CeilingEffectsEntity, RestoreNumber):
    """Brightness of the color light the effects run on."""

    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the slider."""
        super().__init__(entry, "effect_brightness")

    async def async_added_to_hass(self) -> None:
        """Restore the last sent value."""
        await super().async_added_to_hass()
        if (data := await self.async_get_last_number_data()) is not None:
            self._attr_native_value = data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Send the brightness to the lamp."""
        await self._send("setColorLightBrightness", int(value))
        self._attr_native_value = int(value)
        self.async_write_ha_state()
