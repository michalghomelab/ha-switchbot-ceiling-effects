"""Main white light: on/off, brightness and color temperature."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.const import STATE_ON
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import CeilingEffectsEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import CeilingEffectsConfigEntry


def to_percent(brightness: int) -> int:
    """Convert Home Assistant brightness (0-255) to the lamp's 1-100 %."""
    return max(1, min(100, round(brightness / 255 * 100)))


def to_brightness(percent: int) -> int:
    """Convert the lamp's 1-100 % to Home Assistant brightness (0-255)."""
    return round(percent / 100 * 255)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: CeilingEffectsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the white light if the model has one."""
    if entry.runtime_data.lamp.model.white is not None:
        async_add_entities([WhiteLight(entry)])


class WhiteLight(CeilingEffectsEntity, LightEntity, RestoreEntity):
    """The main white light, controlled through the cloud."""

    # The cloud does not report the white light reliably, so the state is
    # what Home Assistant last sent.
    _attr_assumed_state = True
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = frozenset({ColorMode.COLOR_TEMP})

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the light with the model's color temperature range."""
        super().__init__(entry, "white_light")
        white = self._lamp.model.white
        self._attr_min_color_temp_kelvin = white.min_kelvin
        self._attr_max_color_temp_kelvin = white.max_kelvin
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """Restore the last state sent."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is None:
            return
        self._attr_is_on = state.state == STATE_ON
        self._attr_brightness = state.attributes.get(ATTR_BRIGHTNESS)
        self._attr_color_temp_kelvin = state.attributes.get(ATTR_COLOR_TEMP_KELVIN)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the white light on, optionally with brightness and temperature."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        percent = to_percent(brightness) if brightness is not None else None
        await self._run(
            "white light",
            self._lamp.set_white(on=True, brightness=percent, kelvin=kelvin),
        )
        self._attr_is_on = True
        if percent is not None:
            self._attr_brightness = to_brightness(percent)
        if kelvin is not None:
            white = self._lamp.model.white
            self._attr_color_temp_kelvin = max(
                white.min_kelvin, min(white.max_kelvin, kelvin)
            )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the white light off; the color light is left as it is."""
        await self._run("white light", self._lamp.set_white(on=False))
        self._attr_is_on = False
        self.async_write_ha_state()
