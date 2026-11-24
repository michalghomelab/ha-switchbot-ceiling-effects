# SwitchBot Ceiling Effects

Home Assistant custom integration that adds the controls missing from Matter for the
**SwitchBot RGBICWW Ceiling Light**: effects, effect speed and effect brightness, plus
the main white light through the same account.

| Entity | What it does |
| --- | --- |
| `select.<lamp>_effect` | starts one of the effects saved in your SwitchBot account (the presets and the ones you made in the app); `off` turns the color light off |
| `number.<lamp>_effect_speed` | effect speed, 1–100 % (same scale as the SwitchBot app) |
| `number.<lamp>_effect_brightness` | color light brightness, 1–100 % |
| `light.<lamp>_white_light` | main white light: on/off, brightness, color temperature 2700–6500 K |

The white light is also available over Matter, which is local and reports the real
state. Use whichever you prefer; the cloud entity is handy when the lamp is not paired
over Matter or you want everything in one device.

## How it works

The public SwitchBot Cloud API v1.1 can start effects but cannot set their speed
(`setEffectSpeedMode` returns `statusCode 160` for this lamp), and most presets run at
the maximum speed. This integration therefore uses the **private API of the SwitchBot
app**, the same calls the app's lamp screen makes:

- login with your SwitchBot account e-mail and password,
- `command/cmd/api/v1/func/invoke` with the lamp's "thing model" services
  (effect colors `10310`, speed `10309`, brightness `10306`, power `10301`,
  white brightness `10302`, color temperature `10303`, both `10304`),
- the effect list from `wonder/devicestatus/v1/userExternal`.

The API is undocumented and may change with a SwitchBot app update.

## Caveats

- **Write-only.** The entities show the last value sent from Home Assistant (restored
  after a restart). Changes made in the SwitchBot app are not reflected.
- **Effects never touch the white light.** Turning the effect off sends "keep" for the
  white light and "off" for the color light, and the white light entity sends "keep"
  for the color light.
- **The white light state is assumed.** The cloud does not report it reliably (it misses
  changes made over Matter), so the entity shows what Home Assistant last sent.
- **Account password.** It is stored in the config entry, like the encryption-key login
  of the core SwitchBot integration. If it changes, Home Assistant asks for the new one.
  Accounts that sign in with Apple or Google need a password set in the SwitchBot app.
- Needs internet; commands take about a second.
- The effect list is read when the integration starts. Reload it after adding an
  effect in the app.

## Installation

1. HACS → ⋮ → Custom repositories → add
   `https://github.com/michalghomelab/ha-switchbot-ceiling-effects` as **Integration**.
2. Install **SwitchBot Ceiling Effects** and restart Home Assistant.
3. Settings → Devices & services → Add integration → **SwitchBot Ceiling Effects**.
4. Log in with your SwitchBot app e-mail and password and pick the lamp.

Each lamp is its own entry: add the integration again for the next lamp.

Manual install: copy `custom_components/switchbot_ceiling_effects` into your
`config/custom_components/` and restart.

## Example

```yaml
action: select.select_option
target:
  entity_id: select.ceiling_light_effect
data:
  option: Sunset
```

The options are the effect names from the SwitchBot app (e.g. `Romance`, `Dream`,
`Rainbow`, `Sunset`, plus your own effects) and `off`.

## Supported lamps and adding more

| Model | Device type |
| --- | --- |
| RGBICWW Ceiling Light | `W1162000` |

Every model is one entry in
[`models.py`](custom_components/switchbot_ceiling_effects/models.py). To add another
lamp, see [docs/adding-a-lamp.md](docs/adding-a-lamp.md); `tools/sbapp.py` helps read
what you need from the SwitchBot API and app.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements_dev.txt
.venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/ruff format --check .
```
