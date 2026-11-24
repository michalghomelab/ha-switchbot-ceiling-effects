"""
Supported lamp models.

Each SwitchBot model is one `LampModel`: which device type it is and which
"thing model" services of the SwitchBot app API control it. Adding a lamp means
adding one entry to `MODELS`; see docs/adding-a-lamp.md for how to find the values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Properties:
    """
    Thing-model property IDs the cloud keeps for a lamp.

    The lamp itself reports these, so they follow changes made anywhere,
    including over Matter or with a wall switch. Read them through
    `device/device/v1/shadow/getByIDs`.
    """

    white_power: int
    white_brightness: int
    white_kelvin: int
    color_power: int
    color_brightness: int
    color_mode: int
    # Value of `color_mode` that means an effect is running.
    effect_mode: int


@dataclass(frozen=True)
class WhiteLight:
    """Services of a lamp's main white light."""

    set_brightness: int  # params {"0": brightness 1-100}
    set_color_temp: int  # params {"0": kelvin}
    set_brightness_color_temp: int  # params {"0": brightness, "1": kelvin}
    # Parameters for the model's `set_power` service.
    on_params: dict[str, Any]
    off_params: dict[str, Any]
    min_kelvin: int
    max_kelvin: int


@dataclass(frozen=True)
class LampModel:
    """How to control one SwitchBot lamp model through the app API."""

    # `device_detail.device_type` from wonder/device/v3/getdevice, e.g. "W1162000".
    device_type: str
    # Model name shown in Home Assistant.
    name: str
    # `action` for wonder/devicestatus/v1/userExternal that lists the account's
    # preset and custom effects.
    effect_list_action: str
    # Service IDs for command/cmd/api/v1/func/invoke.
    set_effect: int  # params {"0": style, "1": color count, "2": "r:g:b+r:g:b"}
    set_speed: int  # params {"0": speed}
    set_brightness: int  # params {"0": brightness 1-100}
    set_power: int  # params below
    # Parameters for `set_power` that turn the color light off and nothing else.
    color_off_params: dict[str, Any] = field(default_factory=dict)
    speed_min: int = 1
    speed_max: int = 255
    # Speed the SwitchBot app uses before the user changes it.
    default_speed: int = 153
    # Main white light; leave `white` as None for lamps without one.
    white: WhiteLight | None = None
    # Properties to read back; leave as None for a lamp that reports nothing.
    properties: Properties | None = None


# RGBICWW Ceiling Light ("ceilingLight2" in the app, panel plugin CeilingLight2).
CEILING_LIGHT_2 = LampModel(
    device_type="W1162000",
    name="RGBICWW Ceiling Light",
    effect_list_action="getColorfulEffect",
    set_effect=10310,  # setColorLightEffectColors
    set_speed=10309,  # setColorLightEffectSpeed
    set_brightness=10306,  # setColorLightBrightness
    set_power=10301,  # setWhiteAndColorSwitch: per light 0 keep, 1 on, 2 off
    color_off_params={"0": 0, "1": 2, "2": 1},
    white=WhiteLight(
        set_brightness=10302,  # setWhiteBrightness
        set_color_temp=10303,  # setWhiteColorTemp
        set_brightness_color_temp=10304,  # setWhiteBrightnessColorTemp
        on_params={"0": 1, "1": 0, "2": 1},
        off_params={"0": 2, "1": 0, "2": 1},
        # Matter reports 2702-6535 K for this lamp.
        min_kelvin=2700,
        max_kelvin=6500,
    ),
    properties=Properties(
        white_power=10300,
        white_brightness=10302,
        white_kelvin=10303,
        color_power=10301,
        color_brightness=10304,
        color_mode=10305,
        effect_mode=7,  # 2 is a plain color
    ),
)

MODELS: dict[str, LampModel] = {m.device_type: m for m in (CEILING_LIGHT_2,)}
