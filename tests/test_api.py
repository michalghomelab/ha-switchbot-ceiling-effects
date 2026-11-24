"""Tests for the SwitchBot app API client (no Home Assistant needed)."""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types
from collections.abc import Callable
from typing import Any, Self

import aiohttp
import pytest

_PKG = (
    pathlib.Path(__file__).parents[1]
    / "custom_components"
    / "switchbot_ceiling_effects"
)

# Load the modules as a package without the real __init__ (it imports Home
# Assistant), so that their relative imports still resolve.
_package = types.ModuleType("sb_pkg")
_package.__path__ = [str(_PKG)]
sys.modules["sb_pkg"] = _package


def _load(name: str) -> Any:
    """Load one module of the integration on its own."""
    spec = importlib.util.spec_from_file_location(f"sb_pkg.{name}", _PKG / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"sb_pkg.{name}"] = module
    spec.loader.exec_module(module)
    return module


api = _load("api")
models = _load("models")

LOGIN_OK = {"statusCode": 100, "body": {"access_token": "tok", "expires_in": 7200}}
USERINFO_OK = {"statusCode": 100, "body": {"userID": "user-1", "botRegion": "eu"}}
INVOKE_OK = {"resultCode": 100, "data": "req", "message": ""}


class FakeResponse:
    def __init__(self, status: int, data: dict[str, Any]) -> None:
        self.status = status
        self._data = data

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def json(self, content_type: str | None = None) -> dict[str, Any]:  # noqa: ARG002
        return self._data


Handler = Callable[[str, dict[str, Any], dict[str, str]], tuple[int, dict[str, Any]]]


class FakeSession:
    """Answers by URL suffix; records every call."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict, headers: dict, **_: Any) -> FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        for suffix, answer in self.routes.items():
            if url.endswith(suffix):
                if isinstance(answer, Exception):
                    raise answer
                if callable(answer):
                    return FakeResponse(*answer(url, json, headers))
                return FakeResponse(*answer)
        raise AssertionError(url)

    def urls(self) -> list[str]:
        return [c["url"] for c in self.calls]


def account_with(routes: dict[str, Any]) -> tuple[Any, FakeSession]:
    session = FakeSession(
        {"user/login": (200, LOGIN_OK), "user/userinfo": (200, USERINFO_OK), **routes}
    )
    return api.SwitchBotAccount(session, "me@example.com", "pw"), session


def lamp_with(routes: dict[str, Any]) -> tuple[Any, FakeSession]:
    account, session = account_with(routes)
    return api.Lamp(account, models.CEILING_LIGHT_2, "AA:11:BB:22:CC:33"), session


def test_effect_params_encode_colors() -> None:
    effect = api.Effect("Dream", 14, (0xA3E5FF, 0x73F019, 0xFFA8E5))
    assert effect.params() == {
        "0": 14,
        "1": 3,
        "2": "163:229:255+115:240:25+255:168:229",
    }


def test_login_then_invoke_uses_region_token_and_ids() -> None:
    lamp, session = lamp_with({"func/invoke": (200, INVOKE_OK)})
    asyncio.run(lamp.set_speed(30))

    login, _, invoke = session.calls
    assert login["json"]["username"] == "me@example.com"
    assert login["json"]["clientId"] == api.CLIENT_ID
    assert invoke["url"] == (
        "https://wonderlabs.eu.api.switchbot.net/command/cmd/api/v1/func/invoke"
    )
    assert invoke["headers"]["authorization"] == "tok"
    assert invoke["headers"]["UserID"] == "user-1"
    assert invoke["json"]["requestID"] == invoke["headers"]["RequestID"]
    assert invoke["json"]["deviceID"] == "AA11BB22CC33"
    assert invoke["json"]["functionID"] == 10309  # noqa: PLR2004
    assert invoke["json"]["params"] == {"0": 30}


def test_token_is_reused_between_calls() -> None:
    lamp, session = lamp_with({"func/invoke": (200, INVOKE_OK)})
    asyncio.run(lamp.set_speed(30))
    asyncio.run(lamp.set_speed(40))
    assert sum(u.endswith("user/login") for u in session.urls()) == 1


def test_start_effect_sends_colors_then_speed() -> None:
    lamp, session = lamp_with({"func/invoke": (200, INVOKE_OK)})
    effect = api.Effect("Rainbow", 22, (0xFF0000, 0x00FF00))
    asyncio.run(lamp.start_effect(effect, 50))
    invokes = [c["json"] for c in session.calls if c["url"].endswith("func/invoke")]
    assert [(i["functionID"], i["params"]) for i in invokes] == [
        (10310, {"0": 22, "1": 2, "2": "255:0:0+0:255:0"}),
        (10309, {"0": 50}),
    ]


def test_speed_and_brightness_are_clamped() -> None:
    lamp, session = lamp_with({"func/invoke": (200, INVOKE_OK)})
    asyncio.run(lamp.set_speed(999))
    asyncio.run(lamp.set_color_brightness(0))
    params = [c["json"]["params"] for c in session.calls if "invoke" in c["url"]]
    assert params == [{"0": 255}, {"0": 1}]


def test_turn_off_color_light_keeps_white_light() -> None:
    lamp, session = lamp_with({"func/invoke": (200, INVOKE_OK)})
    asyncio.run(lamp.turn_off_color_light())
    invoke = session.calls[-1]["json"]
    assert invoke["functionID"] == 10301  # noqa: PLR2004
    assert invoke["params"]["0"] == 0  # white light: keep as it is
    assert invoke["params"]["1"] == 2  # color light: off  # noqa: PLR2004


def test_rejected_token_logs_in_again_once() -> None:
    answers = iter([(401, {"message": "Unauthorized"}), (200, INVOKE_OK)])
    lamp, session = lamp_with({"func/invoke": lambda *_: next(answers)})
    asyncio.run(lamp.set_speed(30))
    assert sum(u.endswith("user/login") for u in session.urls()) == 2  # noqa: PLR2004


def test_wrong_password_raises_auth_error() -> None:
    account, _ = account_with(
        {"user/login": (200, {"statusCode": 190, "message": "wrong password"})}
    )
    with pytest.raises(api.SwitchBotAuthError, match="wrong password"):
        asyncio.run(account.get_devices())


def test_rejected_command_raises_api_error() -> None:
    lamp, _ = lamp_with({"func/invoke": (200, {"resultCode": 190, "message": "bad"})})
    with pytest.raises(api.SwitchBotApiError, match=r"bad \(code 190\)"):
        asyncio.run(lamp.set_speed(30))


def test_connection_error_is_wrapped() -> None:
    account, _ = account_with({"user/login": aiohttp.ClientConnectionError("boom")})
    with pytest.raises(api.SwitchBotApiError, match="cannot reach"):
        asyncio.run(account.get_devices())


def test_get_devices_reads_type_and_group() -> None:
    items = [
        {
            "device_mac": "AA11BB22CC33",
            "device_name": "Ceiling",
            "groupID": "G1",
            "device_detail": {"device_type": "W1162000"},
        }
    ]
    account, _ = account_with(
        {"device/v3/getdevice": (200, {"statusCode": 100, "body": {"Items": items}})}
    )
    assert asyncio.run(account.get_devices()) == [
        api.Device("AA11BB22CC33", "Ceiling", "W1162000", "G1")
    ]


def test_get_effects_orders_presets_before_custom_and_skips_bad() -> None:
    result = [
        {"name": "Lava", "mode": 63, "color": [1, 2, 3], "type": 1, "index": 0},
        {"name": "Vitality", "mode": 0, "color": [5], "type": 0, "index": 1},
        {"name": "Romance", "mode": 53, "color": [4], "type": 0, "index": 0},
        {"name": "Empty", "mode": 1, "color": [], "type": 1, "index": 1},
    ]
    lamp, session = lamp_with(
        {"userExternal": (200, {"statusCode": 100, "body": {"result": result}})}
    )
    effects = asyncio.run(lamp.get_effects("G1"))
    assert [e.name for e in effects] == ["Romance", "Vitality", "Lava"]
    request = session.calls[-1]["json"]
    assert request["action"] == "getColorfulEffect"
    assert request["groupID"] == "G1"


def test_models_are_keyed_by_device_type() -> None:
    for device_type, model in models.MODELS.items():
        assert model.device_type == device_type
        assert model.speed_min <= model.default_speed <= model.speed_max


FULL_PERCENT = 100


def test_speed_percentages_survive_a_round_trip() -> None:
    model = models.CEILING_LIGHT_2
    for percent in (20, 40, 60, 80, 100):
        speed = model.speed_from_percent(percent)
        assert model.speed_min <= speed <= model.speed_max
        assert model.percent_from_speed(speed) == percent


def test_speed_percentages_stay_within_the_models_range() -> None:
    model = models.CEILING_LIGHT_2
    assert model.speed_from_percent(0) == model.speed_min
    assert model.speed_from_percent(200) == model.speed_max
    assert model.percent_from_speed(0) == 1
    assert model.percent_from_speed(model.speed_max) == FULL_PERCENT


def invokes(session: FakeSession) -> list[tuple[int, dict[str, Any]]]:
    return [
        (c["json"]["functionID"], c["json"]["params"])
        for c in session.calls
        if c["url"].endswith("func/invoke")
    ]


def test_white_on_with_brightness_and_temp_keeps_color_light() -> None:
    lamp, session = lamp_with({"func/invoke": (200, INVOKE_OK)})
    asyncio.run(lamp.set_white(on=True, brightness=40, kelvin=3000))
    assert invokes(session) == [
        (10301, {"0": 1, "1": 0, "2": 1}),  # white on, color light: keep
        (10304, {"0": 40, "1": 3000}),
    ]


def test_white_single_values_use_single_services_and_clamp() -> None:
    lamp, session = lamp_with({"func/invoke": (200, INVOKE_OK)})
    asyncio.run(lamp.set_white(on=True, brightness=150))
    asyncio.run(lamp.set_white(on=True, kelvin=9000))
    assert invokes(session)[1] == (10302, {"0": 100})
    assert invokes(session)[3] == (10303, {"0": 6500})


def test_white_without_a_power_change_only_sends_the_look() -> None:
    lamp, session = lamp_with({"func/invoke": (200, INVOKE_OK)})
    asyncio.run(lamp.set_white(on=None, brightness=40))
    assert invokes(session) == [(10302, {"0": 40})]


def test_white_off_only_sends_power() -> None:
    lamp, session = lamp_with({"func/invoke": (200, INVOKE_OK)})
    asyncio.run(lamp.set_white(on=False, brightness=50))
    assert invokes(session) == [(10301, {"0": 2, "1": 0, "2": 1})]


def test_model_without_white_light_refuses() -> None:
    model = models.LampModel(
        device_type="X",
        name="No white",
        effect_list_action="a",
        set_effect=1,
        set_speed=2,
        set_brightness=3,
        set_color_rgb=5,
        set_power=4,
    )
    account, session = account_with({})
    lamp = api.Lamp(account, model, "AA")
    with pytest.raises(api.SwitchBotApiError, match="no white light"):
        asyncio.run(lamp.set_white(on=True))
    assert session.calls == []


SHADOW_OK = {
    "resultCode": 100,
    "data": {
        "10300": {"id": 10300, "value": 1},
        "10301": {"id": 10301, "value": 0},
        "10302": {"id": 10302, "value": 83},
        "10303": {"id": 10303, "value": 3984},
        "10304": {"id": 10304, "value": 100},
        "10306": {"id": 10306, "value": "163:229:255"},
        "10305": {"id": 10305, "value": 7},
    },
}


def test_get_state_reads_what_the_lamp_reports() -> None:
    lamp, session = lamp_with({"shadow/getByIDs": (200, SHADOW_OK)})
    state = asyncio.run(lamp.get_state())
    assert state == api.LampState(
        white_on=True,
        white_brightness=83,
        white_kelvin=3984,
        color_on=False,
        color_brightness=100,
        color_rgb=(163, 229, 255),
        effect_running=True,
    )
    request = session.calls[-1]["json"]
    assert request["deviceID"] == "AA11BB22CC33"
    assert sorted(request["propertyIDs"]) == [
        10300,
        10301,
        10302,
        10303,
        10304,
        10305,
        10306,
    ]
    assert "requestID" not in request


def test_get_state_keeps_unknown_values_as_none() -> None:
    shadow = {
        "resultCode": 100,
        "data": {"10300": {"value": None}, "10305": {"value": 2}},
    }
    lamp, _ = lamp_with({"shadow/getByIDs": (200, shadow)})
    state = asyncio.run(lamp.get_state())
    assert state.white_on is None
    assert state.white_brightness is None
    assert state.effect_running is False  # a plain color, not an effect


def test_get_state_without_properties_is_empty() -> None:
    model = models.LampModel(
        device_type="X",
        name="No readback",
        effect_list_action="a",
        set_effect=1,
        set_speed=2,
        set_brightness=3,
        set_color_rgb=5,
        set_power=4,
    )
    account, session = account_with({})
    state = asyncio.run(api.Lamp(account, model, "AA").get_state())
    assert state == api.LampState()
    assert session.calls == []


class FakeBle:
    """Stands in for the Bluetooth backend."""

    def __init__(self, *, available: bool = True, fail: bool = False) -> None:
        self.available = available
        self.fail = fail
        self.sent: list[list[str]] = []

    async def send(self, commands: list[str]) -> None:
        self.sent.append(commands)
        if self.fail:
            msg = "no answer"
            raise api.SwitchBotBleError(msg)


def ble_lamp(**kwargs: Any) -> tuple[Any, FakeBle, FakeSession]:
    account, session = account_with({"func/invoke": (200, INVOKE_OK)})
    ble = FakeBle(**kwargs)
    lamp = api.Lamp(account, models.CEILING_LIGHT_2, "AA:11:BB:22:CC:33", ble)
    return lamp, ble, session


def test_effect_as_bluetooth_packets() -> None:
    effect = api.Effect("Dream", 14, (0xA3E5FF, 0x73F019, 0xFFA8E5))
    # The same bytes pySwitchbot sends for this effect.
    assert effect.ble_packets(models.CEILING_LIGHT_2.ble) == [
        "570F490D010E0300A3E5FF73F019FFA8E5"
    ]


def test_effect_colors_are_split_across_packets() -> None:
    effect = api.Effect("Rainbow", 22, (0xFF0000, 0x00FF00, 0x0000FF, 0x123456))
    assert effect.ble_packets(models.CEILING_LIGHT_2.ble) == [
        "570F490D01160400FF000000FF000000FF",
        "570F490D01160401123456",
    ]


def test_bluetooth_is_used_before_the_cloud() -> None:
    lamp, ble, session = ble_lamp()
    asyncio.run(lamp.set_speed(30))
    assert ble.sent == [["570F490D031E"]]
    assert invokes(session) == []


def test_cloud_takes_over_when_bluetooth_fails() -> None:
    lamp, ble, session = ble_lamp(fail=True)
    asyncio.run(lamp.set_speed(30))
    assert ble.sent == [["570F490D031E"]]
    assert invokes(session) == [(10309, {"0": 30})]


def test_cloud_is_used_when_the_lamp_is_out_of_range() -> None:
    lamp, ble, session = ble_lamp(available=False)
    asyncio.run(lamp.set_color_brightness(22))
    assert ble.sent == []
    assert invokes(session) == [(10306, {"0": 22})]


def test_white_over_bluetooth_keeps_the_color_light() -> None:
    lamp, ble, _ = ble_lamp()
    asyncio.run(lamp.set_white(on=True, brightness=40, kelvin=3000))
    # 0x81: bit 7 says "literally", white on (1), color light kept (0).
    assert ble.sent == [["570F49010181"], ["570F490111280BB8"]]


def test_white_brightness_over_bluetooth_leaves_the_power_alone() -> None:
    lamp, ble, _ = ble_lamp()
    asyncio.run(lamp.set_white(on=None, brightness=40))
    # No power command: it would end the effect the color light is running.
    assert ble.sent == [["570F49010928"]]


def test_turn_off_color_light_over_bluetooth() -> None:
    lamp, ble, _ = ble_lamp()
    asyncio.run(lamp.turn_off_color_light())
    # 0x88: color light off (2 << 2), white light kept.
    assert ble.sent == [["570F49010188"]]


def test_start_effect_sends_colors_then_speed_over_bluetooth() -> None:
    lamp, ble, _ = ble_lamp()
    asyncio.run(lamp.start_effect(api.Effect("Dream", 14, (0xA3E5FF,)), 250))
    assert ble.sent == [["570F490D010E0100A3E5FF"], ["570F490D03FA"]]


def test_state_from_a_bluetooth_broadcast() -> None:
    """The lamp's own broadcast carries both sub-lights."""
    props = models.CEILING_LIGHT_2.properties
    state = api.state_from_advertisement(
        {
            "isOn": True,
            "brightness": 55,
            "color_mode": 7,
            "cw": 3984,
            "main_isOn": False,
            "main_brightness": 2,
        },
        props,
    )
    assert state == api.LampState(
        white_on=False,
        white_brightness=2,
        white_kelvin=3984,
        color_on=True,
        color_brightness=55,
        effect_running=True,
    )


def test_addresses_for_the_cloud_and_for_bluetooth() -> None:
    """The cloud wants the MAC without separators, Home Assistant with them."""
    for written in ("AC276E591656", "ac:27:6e:59:16:56", "AC-27-6E-59-16-56"):
        assert api.compact_mac(written) == "AC276E591656"
        assert api.ble_address(written) == "AC:27:6E:59:16:56"
