"""Effect speed and color light brightness."""

from __future__ import annotations

from collections.abc import Callable  # noqa: TC003 - needed at runtime by the dataclass
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import PERCENTAGE

from .entity import CeilingEffectsEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import CeilingEffectsConfigEntry


@dataclass(frozen=True, kw_only=True)
class CeilingNumberDescription(NumberEntityDescription):
    """Number entity bound to one API command."""

    command: str
    to_parameter: Callable[[int], Any]


NUMBERS = (
    CeilingNumberDescription(
        key="effect_speed",
        command="setEffectSpeedMode",
        to_parameter=lambda value: {"speed": value},
        native_min_value=1,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CeilingNumberDescription(
        key="effect_brightness",
        command="setColorLightBrightness",
        to_parameter=lambda value: value,
        native_min_value=1,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: CeilingEffectsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add speed and brightness sliders."""
    async_add_entities(CeilingNumber(entry, description) for description in NUMBERS)


class CeilingNumber(CeilingEffectsEntity, RestoreNumber):
    """Slider that sends its value to the lamp."""

    entity_description: CeilingNumberDescription

    def __init__(
        self, entry: CeilingEffectsConfigEntry, description: CeilingNumberDescription
    ) -> None:
        """Initialize the slider."""
        super().__init__(entry, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        """Restore the last sent value."""
        await super().async_added_to_hass()
        if (data := await self.async_get_last_number_data()) is not None:
            self._attr_native_value = data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Send the value to the lamp."""
        description = self.entity_description
        await self._send(description.command, description.to_parameter(int(value)))
        self._attr_native_value = int(value)
        self.async_write_ha_state()
