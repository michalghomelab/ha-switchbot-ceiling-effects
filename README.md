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

**Commands go out over Bluetooth** when the lamp is in range of a Bluetooth adapter or
an ESPHome proxy: local, instant, no cloud. The cloud takes over automatically when the
lamp is out of range.

**The state comes from the lamp's own Bluetooth broadcasts**, so it updates within
seconds and without the cloud: both sub-lights, their brightness, the white light's
color temperature and whether an effect is running. While broadcasts arrive, the cloud
is not asked at all; out of range the integration falls back to reading the state the
lamp reports to the cloud, every 30 seconds and right after each command.

Either way, changes made anywhere, in the SwitchBot app, over Matter or with a wall
switch, show up in Home Assistant.

The white light is also available over Matter, which is local and updates instantly.
Use whichever you prefer; the cloud entity is handy when the lamp is not paired over
Matter or you want everything in one device.

## How it works

The public SwitchBot Cloud API v1.1 can start effects but cannot set their speed
(`setEffectSpeedMode` returns `statusCode 160` for this lamp), and most presets run at
the maximum speed. This integration therefore speaks to the lamp the way the SwitchBot
app does.

**Over Bluetooth** (preferred), through [pySwitchbot] and Home Assistant's Bluetooth
stack, so any adapter or ESPHome proxy in range will do. The commands are the same
bytes the app sends when your phone is next to the lamp, for example `570F490D03<speed>`
for the effect speed. The lamp's Bluetooth key is read from your account once, when you
add the lamp.

**Through the cloud** when the lamp is out of Bluetooth range, using the app's private
API:

- login with your SwitchBot account e-mail and password,
- `command/cmd/api/v1/func/invoke` with the lamp's "thing model" services
  (effect colors `10310`, speed `10309`, brightness `10306`, power `10301`,
  white brightness `10302`, color temperature `10303`, both `10304`),
- the state from `device/device/v1/shadow/getByIDs` (white `10300`/`10302`/`10303`,
  color light `10301`/`10304`/`10305`), only while the lamp is out of Bluetooth range,
- the effect list from `wonder/devicestatus/v1/userExternal`.

The cloud API is undocumented and may change with a SwitchBot app update.

[pySwitchbot]: https://github.com/sblibs/pySwitchbot

## Caveats

- **Two values are not reported by the lamp:** the effect speed, and which effect is
  running. The speed slider shows what was last sent (restored after a restart), and the
  effect selector shows the running effect only when Home Assistant started it. An effect
  started in the SwitchBot app makes it `unknown`; the lamp only says that *some* effect
  is running.
- **Effects never touch the white light.** Turning the effect off sends "keep" for the
  white light and "off" for the color light, and the white light entity sends "keep"
  for the color light.
- **Account password.** It is stored in the config entry, like the encryption-key login
  of the core SwitchBot integration. If it changes, Home Assistant asks for the new one.
  Accounts that sign in with Apple or Google need a password set in the SwitchBot app.
- **Without Bluetooth in range** everything still works, but each command needs
  internet and takes about a second, and the state is polled from the cloud.
- The effect list is read when the integration starts. Reload it after adding an
  effect in the app.

## Bluetooth or the cloud?

Home Assistant logs which one it used. Turn on debug logging for the integration
(Settings → Devices & services → SwitchBot Ceiling Effects → ⋮ → Enable debug logging)
and look for `Sent 1 command(s) ... over Bluetooth`. A line saying
`Bluetooth failed ..., using the cloud instead` means the lamp was out of range or the
connection dropped.

A lamp added before version 0.3.0 has no Bluetooth key stored; the integration reads one
on the next restart, so no need to add the lamp again.

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
