# Adding another SwitchBot lamp

The integration is split into two layers:

- **`api.py`** talks to the private SwitchBot app API: login, device list, effect
  list and `func/invoke`. It knows nothing about a particular lamp.
- **`models.py`** has one `LampModel` per supported lamp: its device type and the
  service IDs that control it. The config flow offers every lamp on the account whose
  device type is in `MODELS`.

Each lamp is its own config entry: add the integration again for every lamp,
and the flow lists only the lamps that are not set up yet. Supporting a new model
usually means adding one `LampModel` to `models.py`. You only touch other code if the
lamp needs a control the ceiling light doesn't have.

## What you need to find

| `LampModel` field | Where it comes from |
| --- | --- |
| `device_type` | `device_detail.device_type` in the device list |
| `effect_list_action` | `action` the panel sends to `wonder/devicestatus/v1/userExternal` |
| `set_effect`, `set_speed`, `set_brightness`, `set_power` | service IDs (`PMLightService` or similar) in the panel plugin |
| `color_off_params` | how the panel calls the power service for the color light only |
| `speed_min`, `speed_max`, `default_speed` | the speed slider in the panel plugin (`min`, `max`, default value) |
| `white` (optional `WhiteLight`) | white brightness / color temperature services, power parameters for the white light only, and the Kelvin range (Matter reports it, if the lamp has Matter) |

## 1. Log in and find the device type

`tools/sbapp.py` uses only the Python standard library. Run it in a terminal; it
asks for the e-mail and password and saves only the session token, with access
for your user only, to `.sbapp_session.json` in the current directory (ignored by git).

```sh
python3 tools/sbapp.py login
python3 tools/sbapp.py devices
# AA11BB22CC33  type=W1162000  group=G01-...  name=Ceiling
```

## 2. Find the model in the SwitchBot app

Download a **current** Android build of the SwitchBot app (old builds don't know new
lamps), for example with [apkeep](https://github.com/EFForg/apkeep):

```sh
apkeep -l -d apk-pure -a com.theswitchbot.switchbot          # list versions
apkeep -d apk-pure -o acknowledge_dangers=true \
       -a com.theswitchbot.switchbot@10.11 apk/
```

An `.xapk` is a zip: unzip it, then unzip `com.theswitchbot.switchbot.apk` inside it.
Look at `assets/jsCode/`:

- `ble_parse_rule.json` maps the device type to an internal name:
  `{"t": "W1162000", ..., "rg": "ceilingLight2"}`.
- `main.js` dispatches by device type to `call<Name>Service`, `read<Name>Property`
  and `write<Name>Property`.
- `wo<Name>.js` (here `woCeilingLight2.js`) lists the service IDs and shows how each
  is encoded for Bluetooth, which tells you what the parameters mean. When the phone
  is not next to the lamp, the same service ID and parameters go to the cloud through
  `commonIotService` → `command/cmd/api/v1/func/invoke`.

## 3. Read the panel plugin

The device screen in the app is a React Native plugin downloaded at runtime:

```sh
python3 tools/sbapp.py plugins
# CeilingLight2   https://publish-artifact.switchbot.net/RN/CeilingLight2_v1.0.12.0_android.zip
```

Download the zip, unzip it, then unzip the `bundle.zip` inside. Search
`index.android.bundle` for:

- the service enum, e.g. `PMLightService` with `setColorLightEffectSpeed="10309"`,
- `callDMService(...)` calls, to see the parameters (`{0: speed}`; for power
  `{0: white, 1: color, 2: 1}` with 0 = keep, 1 = on, 2 = off),
- the speed slider (`min:1,max:255`) and the default speed,
- `operateUserExternal({... action: "getColorfulEffect" ...})`, the effect list.

## 4. Check the effect list

```sh
python3 tools/sbapp.py effects AA11BB22CC33 G01-... getColorfulEffect
```

Each effect has `name`, `mode` (style number), `color` (list of `0xRRGGBB` integers)
and `rate` (factory speed). `type` 0 is a preset, 1 is an effect the user made in the
app. The integration sends `{"0": mode, "1": color count, "2": "r:g:b+r:g:b"}` to the
set-effect service, then the speed.

## 5. Test on the lamp

`invoke` changes the real lamp, so check what the service does in `wo<Name>.js` first,
especially whether it can touch a light you don't want changed.

```sh
python3 tools/sbapp.py invoke AA11BB22CC33 10309 '{"0": 30}'
# {"resultCode": 100, "data": "<request id>", ...}
```

`resultCode 100` means the cloud accepted the command. The lamp's own result comes back
over MQTT, which the script doesn't read, so look at the lamp to see what happened.
`shadow` reads the stored properties (e.g. `10301` color light on/off), but some values,
such as the speed, are only updated by the app and may be stale.

## 6. Add the model

```python
STRIP_LIGHT_3 = LampModel(
    device_type="W...",
    name="...",
    effect_list_action="...",
    set_effect=...,
    set_speed=...,
    set_brightness=...,
    set_power=...,
    color_off_params={...},
)

MODELS = {m.device_type: m for m in (CEILING_LIGHT_2, STRIP_LIGHT_3)}
```

Then run the tests (`.venv/bin/pytest`), restart Home Assistant and add the integration
again; the new lamp shows up in the list.
