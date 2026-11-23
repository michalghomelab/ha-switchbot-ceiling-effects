"""Tests for the SwitchBot API client (no Home Assistant needed)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import importlib.util
import pathlib
import sys
from typing import Any, Self

import aiohttp
import pytest

# Load api.py directly so the package __init__ (which imports homeassistant) is skipped.
_API_PATH = (
    pathlib.Path(__file__).parents[1]
    / "custom_components"
    / "switchbot_ceiling_effects"
    / "api.py"
)
_spec = importlib.util.spec_from_file_location("sb_api", _API_PATH)
api = importlib.util.module_from_spec(_spec)
sys.modules["sb_api"] = api
_spec.loader.exec_module(api)


class FakeResponse:
    def __init__(self, status: int, data: dict[str, Any]) -> None:
        self.status = status
        self._data = data

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:  # noqa: PLR2004
            raise aiohttp.ClientResponseError(None, (), status=self.status)

    async def json(self, content_type: str | None = None) -> dict[str, Any]:  # noqa: ARG002
        return self._data


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_sign_headers_matches_reference() -> None:
    headers = api.sign_headers("tok", "sec", t="1700000000000", nonce="n-1")
    expected = base64.b64encode(
        hmac.new(b"sec", b"tok1700000000000n-1", hashlib.sha256).digest()
    ).decode()
    assert headers["Authorization"] == "tok"
    assert headers["sign"] == expected
    assert headers["t"] == "1700000000000"
    assert headers["nonce"] == "n-1"


def test_send_effect_command_payload() -> None:
    session = FakeSession(FakeResponse(200, {"statusCode": 100, "body": {}}))
    client = api.SwitchBotApi(session, "tok", "sec")
    asyncio.run(client.send_command("DEV1", "setLightEffect", {"effectId": 15}))
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://api.switch-bot.com/v1.1/devices/DEV1/commands"
    assert call["json"] == {
        "commandType": "command",
        "command": "setLightEffect",
        "parameter": {"effectId": 15},
    }


def test_get_devices() -> None:
    devices = [{"deviceId": "A", "deviceType": "RGBICWW Ceiling Light"}]
    session = FakeSession(
        FakeResponse(200, {"statusCode": 100, "body": {"deviceList": devices}})
    )
    client = api.SwitchBotApi(session, "tok", "sec")
    assert asyncio.run(client.get_devices()) == devices


def test_unsupported_command_raises_readable_error() -> None:
    session = FakeSession(FakeResponse(200, {"statusCode": 160, "message": "x"}))
    client = api.SwitchBotApi(session, "tok", "sec")
    with pytest.raises(api.SwitchBotApiError, match=r"not supported.*160"):
        asyncio.run(client.send_command("DEV1", "setEffectSpeedMode", {"speed": 9}))


def test_unauthorized_raises_auth_error() -> None:
    session = FakeSession(FakeResponse(401, {"message": "Unauthorized"}))
    client = api.SwitchBotApi(session, "tok", "sec")
    with pytest.raises(api.SwitchBotAuthError):
        asyncio.run(client.get_devices())


def test_connection_error_is_wrapped() -> None:
    session = FakeSession(aiohttp.ClientConnectionError("boom"))
    client = api.SwitchBotApi(session, "tok", "sec")
    with pytest.raises(api.SwitchBotApiError, match="cannot reach"):
        asyncio.run(client.get_devices())
