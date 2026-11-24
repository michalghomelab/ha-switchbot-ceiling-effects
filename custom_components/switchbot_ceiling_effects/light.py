"""The lamp's two lights: the main white one and the color one with effects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
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
    """Add the color light, and the white light if the model has one."""
    lights: list[CeilingEffectsEntity] = [ColorLight(entry)]
    if entry.runtime_data.lamp.model.white is not None:
        lights.append(WhiteLight(entry))
    async_add_entities(lights)


class WhiteLight(CeilingEffectsEntity, LightEntity):
    """The main white light, as the lamp reports it."""

    _attr_color_mode = ColorMode.COLOR_TEMP
    # A plain set: with an effect running Home Assistant adds a mode to a copy
    # of it, which a frozenset does not allow.
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.COLOR_TEMP}

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
                # Telling the lamp to switch a light on makes it drop the
                # effect the color light is running, so a light that is
                # already on is sent its new look and nothing else.
                on=None if self.is_on else True,
                brightness=None if brightness is None else to_percent(brightness),
                kelvin=kwargs.get(ATTR_COLOR_TEMP_KELVIN),
            ),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the white light off; the color light is left as it is."""
        await self._run("white light", self._lamp.set_white(on=False))


class ColorLight(CeilingEffectsEntity, LightEntity):
    """
    The color light, with the effects saved in the SwitchBot account.

    Home Assistant shows the effects in the light's own dialog, next to the
    brightness and the color. The lamp reports whether an effect is running,
    but not which one, so the name is the one this integration last sent.
    """

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, entry: CeilingEffectsConfigEntry) -> None:
        """Initialize the light with the effects of this account."""
        super().__init__(entry, "color_light")
        self._attr_effect_list = list(self.coordinator.effects)

    @property
    def is_on(self) -> bool | None:
        """Whether the lamp reports the color light as on."""
        return self.coordinator.data.color_on

    @property
    def brightness(self) -> int | None:
        """Brightness the lamp reports, on Home Assistant's 0-255 scale."""
        percent = self.coordinator.data.color_brightness
        return None if percent is None else to_brightness(percent)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """The last colour known; broadcasts do not carry one."""
        return self.coordinator.color_rgb

    @property
    def effect(self) -> str | None:
        """The running effect, if this integration started it."""
        if self.coordinator.data.effect_running is False:
            return None
        return self.coordinator.effect_name

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start an effect, set a color or a brightness, or just switch on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        percent = None if brightness is None else to_percent(brightness)

        if (effect := kwargs.get(ATTR_EFFECT)) in self.coordinator.effects:
            await self._run(
                "effect",
                self._lamp.start_effect(
                    self.coordinator.effects[effect], self.coordinator.speed
                ),
            )
            self.coordinator.effect_name = effect
        elif (rgb := kwargs.get(ATTR_RGB_COLOR)) is not None:
            await self._run("color", self._lamp.set_color_rgb(*rgb))
            self.coordinator.color_rgb = rgb
            self.coordinator.effect_name = None
        elif percent is None:
            await self._run("color light", self._lamp.switch_color_light(on=True))

        if percent is not None:
            await self._run("brightness", self._lamp.set_color_brightness(percent))
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the color light off; the white light is left as it is."""
        await self._run("color light", self._lamp.turn_off_color_light())
        self.coordinator.effect_name = None
