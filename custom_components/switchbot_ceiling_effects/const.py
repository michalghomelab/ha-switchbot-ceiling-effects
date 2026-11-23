"""Constants for SwitchBot Ceiling Effects."""

DOMAIN = "switchbot_ceiling_effects"

CONF_SECRET = "secret"  # noqa: S105

DEVICE_TYPE = "RGBICWW Ceiling Light"

EFFECT_OFF = "off"

# Index in this list is the API effectId (0-25), see
# https://github.com/OpenWonderLabs/SwitchBotAPI/blob/main/devices/lighting/rgbicww-ceiling-light.md
EFFECTS = [
    "romance",
    "vitality",
    "heartthrob",
    "party",
    "dynamic",
    "mystery",
    "lightning",
    "rock",
    "starlight",
    "valentines_day",
    "dream",
    "alarm",
    "fireworks",
    "waves",
    "christmas",
    "rainbow",
    "game",
    "halloween",
    "meditation",
    "starlit_sky",
    "sleep",
    "film",
    "sunrise",
    "sunset",
    "new_year",
    "cherry_blossom",
]
