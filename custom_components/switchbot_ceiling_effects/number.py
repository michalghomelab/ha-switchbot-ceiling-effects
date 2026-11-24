"""Effect speed, as a slider for the exact value."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
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
    """Add the speed slider."""
    async_add_entities([EffectSpeed(entry)])


class CeilingNumber(CeilingEffectsEntity, NumberEntity):
    """A 1-100 % slider."""

    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER


class EffectSpeed(CeilingNumber, RestoreNumber):
    """
    Effect speed, shown as a percentage like in the SwitchBot app.

    The lamp does not report the speed, so the value is the one last sent,
    which the color light also sets from its own list of speeds.
    """

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the slider."""
        super().__init__(entry, "effect_speed")

    @property
    def native_value(self) -> float:
        """The speed last sent, as a percentage."""
        return self._lamp.model.percent_from_speed(self.coordinator.speed)

    async def async_added_to_hass(self) -> None:
        """Restore the speed, so it survives a restart."""
        await super().async_added_to_hass()
        data = await self.async_get_last_number_data()
        if data is not None and data.native_value is not None:
            self.coordinator.speed = self._lamp.model.speed_from_percent(
                data.native_value
            )

    async def async_set_native_value(self, value: float) -> None:
        """Send the speed to the lamp; it also applies to the next effect."""
        speed = self._lamp.model.speed_from_percent(value)
        await self._run("speed", self._lamp.set_speed(speed))
        self.coordinator.speed = speed
        self.coordinator.async_update_listeners()
