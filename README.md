# SwitchBot Ceiling Effects

Home Assistant custom integration that adds the controls missing from Matter for the
**SwitchBot RGBICWW Ceiling Light**:

| Entity | What it does | API command |
| --- | --- | --- |
| `select.<lamp>_effect` | starts one of the 26 preset effects from the app | `setLightEffect` |
| `number.<lamp>_effect_speed` | effect speed, 1–255 | `setEffectSpeedMode` |
| `number.<lamp>_effect_brightness` | color light brightness, 1–100 % | `setColorLightBrightness` |

Everything else (on/off, main light brightness, color temperature, state) stays with the
Matter integration, which is local and real-time. This integration only sends commands
through the SwitchBot Cloud API v1.1: no polling, no webhooks, no MQTT.

## Caveats

- **Write-only.** The API does not report the running effect or its speed, so the entities
  show the last value sent from Home Assistant (restored after a restart). Changes made in
  the SwitchBot app are not reflected.
- **Speed is undocumented for this model.** `setEffectSpeedMode` is documented only for
  RGBICWW Light Bars. If the cloud rejects it for the ceiling light, the slider raises an
  error such as `command not supported by this device (statusCode 160)`.
- Needs internet; commands take about a second. Every command counts towards the
  10,000 calls/day API limit.

## Installation

1. HACS → ⋮ → Custom repositories → add
   `https://github.com/michalghomelab/ha-switchbot-ceiling-effects` as **Integration**.
2. Install **SwitchBot Ceiling Effects** and restart Home Assistant.
3. Settings → Devices & services → Add integration → **SwitchBot Ceiling Effects**.
4. Enter the token and secret from the SwitchBot app: Profile → Preferences → tap
   *App Version* 10 times → *Developer Options*.

Manual install: copy `custom_components/switchbot_ceiling_effects` into your
`config/custom_components/` and restart.

## Example

```yaml
action: select.select_option
target:
  entity_id: select.ceiling_light_effect
data:
  option: sunrise
```

Effect keys: `romance`, `vitality`, `heartthrob`, `party`, `dynamic`, `mystery`,
`lightning`, `rock`, `starlight`, `valentines_day`, `dream`, `alarm`, `fireworks`, `waves`,
`christmas`, `rainbow`, `game`, `halloween`, `meditation`, `starlit_sky`, `sleep`, `film`,
`sunrise`, `sunset`, `new_year`, `cherry_blossom`.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements_dev.txt
.venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/ruff format --check .
```
