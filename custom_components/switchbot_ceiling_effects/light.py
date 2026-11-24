"""Main white light: on/off, brightness and color temperature."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)

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


class WhiteLight(CeilingEffectsEntity, LightEntity):
    """The main white light, as the lamp reports it to the cloud."""

    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = frozenset({ColorMode.COLOR_TEMP})

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the light with the model's color temperature range."""
        super().__init__(entry, "white_light")
        white = self._lamp.model.white
        self._attr_min_color_temp_kelvin = white.min_kelvin
        self._attr_max_color_temp_kelvin = white.max_kelvin

    @property
    def is_on(self) -> bool | None:
        """Whether the lamp reports the white light as on."""
        return self.coordinator.data.white_on

    @property
    def brightness(self) -> int | None:
        """Brightness the lamp reports, on Home Assistant's 0-255 scale."""
        percent = self.coordinator.data.white_brightness
        return None if percent is None else to_brightness(percent)

    @property
    def color_temp_kelvin(self) -> int | None:
        """Color temperature the lamp reports."""
        return self.coordinator.data.white_kelvin

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the white light on, optionally with brightness and temperature."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        await self._run(
            "white light",
            self._lamp.set_white(
                on=True,
                brightness=None if brightness is None else to_percent(brightness),
                kelvin=kwargs.get(ATTR_COLOR_TEMP_KELVIN),
            ),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the white light off; the color light is left as it is."""
        await self._run("white light", self._lamp.set_white(on=False))
