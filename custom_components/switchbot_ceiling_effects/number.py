"""Color light brightness and effect speed."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import PERCENTAGE

from .entity import CeilingEffectsEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import CeilingEffectsConfigEntry
    from .models import LampModel


def speed_to_percent(model: LampModel, speed: int) -> int:
    """Convert an API speed to the percentage the SwitchBot app shows."""
    return max(1, round(speed / model.speed_max * 100))


def percent_to_speed(model: LampModel, percent: float) -> int:
    """Convert a percentage (1-100) to an API speed within the model's range."""
    speed = round(percent / 100 * model.speed_max)
    return max(model.speed_min, min(model.speed_max, speed))


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: CeilingEffectsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the brightness and speed sliders."""
    async_add_entities([EffectBrightness(entry), EffectSpeed(entry)])


class CeilingNumber(CeilingEffectsEntity, NumberEntity):
    """A 1-100 % slider."""

    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER


class EffectBrightness(CeilingNumber):
    """Brightness of the color light, as the lamp reports it."""

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the slider."""
        super().__init__(entry, "effect_brightness")

    @property
    def native_value(self) -> float | None:
        """Brightness the lamp reports."""
        return self.coordinator.data.color_brightness

    async def async_set_native_value(self, value: float) -> None:
        """Send the brightness to the lamp."""
        await self._run("brightness", self._lamp.set_color_brightness(int(value)))


class EffectSpeed(CeilingNumber, RestoreNumber):
    """
    Effect speed, shown as a percentage like in the SwitchBot app.

    The lamp does not report the speed, so this is the value last sent.
    """

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the slider at the app's default speed."""
        super().__init__(entry, "effect_speed")
        model = self._lamp.model
        self._attr_native_value = speed_to_percent(model, model.default_speed)

    async def async_added_to_hass(self) -> None:
        """Restore the speed and share it with the effect selector."""
        await super().async_added_to_hass()
        data = await self.async_get_last_number_data()
        if data is not None and data.native_value is not None:
            self._attr_native_value = data.native_value
            self.coordinator.speed = percent_to_speed(
                self._lamp.model, data.native_value
            )

    async def async_set_native_value(self, value: float) -> None:
        """Send the speed to the lamp; it also applies to the next effect."""
        speed = percent_to_speed(self._lamp.model, value)
        await self._run("speed", self._lamp.set_speed(speed))
        self.coordinator.speed = speed
        self._attr_native_value = int(value)
        self.async_write_ha_state()
