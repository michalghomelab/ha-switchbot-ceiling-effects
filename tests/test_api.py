"""Tests for the SwitchBot app API client (no Home Assistant needed)."""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
from collections.abc import Callable
from typing import Any, Self

import aiohttp
import pytest

_PKG = (
    pathlib.Path(__file__).parents[1]
    / "custom_components"
    / "switchbot_ceiling_effects"
)


def _load(name: str) -> Any:
    """Load a module directly so the package __init__ (Home Assistant) is skipped."""
    spec = importlib.util.spec_from_file_location(f"sb_{name}", _PKG / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"sb_{name}"] = module
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
