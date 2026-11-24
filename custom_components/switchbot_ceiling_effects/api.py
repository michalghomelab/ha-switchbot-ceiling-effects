"""
Client for the private SwitchBot app API (the one the SwitchBot app itself uses).

The public Cloud API v1.1 cannot set the effect speed, so everything here goes
through the app's "thing model" services instead. Endpoints and parameters come
from the SwitchBot app (v10.11) and its React Native panel plugins.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from .models import LampModel

# Public client ID of the SwitchBot app, also used by pySwitchbot.
CLIENT_ID = "5nnwmhmsa9xxskm14hd85lm9bm"
LOGIN_URL = "https://account.api.switchbot.net/account/api/v1/user/login"
USERINFO_URL = "https://account.api.switchbot.net/account/api/v1/user/userinfo"
API_HOST = "https://wonderlabs.{region}.api.switchbot.net"

STATUS_OK = 100
TIMEOUT = aiohttp.ClientTimeout(total=15)
HTTP_UNAUTHORIZED = (401, 403)
TOKEN_MARGIN = 300  # log in again this many seconds before the token expires


class SwitchBotApiError(Exception):
    """Raised when a SwitchBot API call fails."""


class SwitchBotAuthError(SwitchBotApiError):
    """Raised when the e-mail or password is rejected."""


@dataclass(frozen=True)
class Device:
    """A device on the SwitchBot account."""

    mac: str
    name: str
    device_type: str
    group_id: str


@dataclass(frozen=True)
class Effect:
    """A preset or custom effect as stored in the SwitchBot account."""

    name: str
    mode: int
    colors: tuple[int, ...]

    def params(self) -> dict[str, Any]:
        """Parameters for the set-effect service: style, color count, colors."""
        rgb = "+".join(
            f"{c >> 16 & 0xFF}:{c >> 8 & 0xFF}:{c & 0xFF}" for c in self.colors
        )
        return {"0": self.mode, "1": len(self.colors), "2": rgb}


def compact_mac(mac: str) -> str:
    """Return the MAC the API uses as device ID: upper case, no separators."""
    return mac.replace(":", "").replace("-", "").upper()


class SwitchBotAccount:
    """Logs in with the SwitchBot account and calls the app API."""

    def __init__(
        self, session: aiohttp.ClientSession, email: str, password: str
    ) -> None:
        """Store the session and credentials; log in lazily."""
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._expires = 0.0
        self.user_id = ""
        self.region = ""

    async def _post(
        self, url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        try:
            async with self._session.post(
                url, json=body, headers=headers, timeout=TIMEOUT
            ) as resp:
                data = await resp.json(content_type=None)
                return resp.status, data if isinstance(data, dict) else {}
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            msg = f"cannot reach SwitchBot: {err}"
            raise SwitchBotApiError(msg) from err

    async def login(self) -> None:
        """Get a fresh access token, the user ID and the account region."""
        status, data = await self._post(
            LOGIN_URL,
            {
                "clientId": CLIENT_ID,
                "username": self._email,
                "password": self._password,
                "grantType": "password",
                "verifyCode": "",
            },
            {},
        )
        if status in HTTP_UNAUTHORIZED or data.get("statusCode") != STATUS_OK:
            msg = f"login failed: {data.get('message') or status}"
            raise SwitchBotAuthError(msg)
        auth = data.get("body") or {}
        token = auth.get("access_token")
        if not token:
            msg = "login response has no access token"
            raise SwitchBotAuthError(msg)

        _, info = await self._post(USERINFO_URL, {}, {"authorization": token})
        user = info.get("body") or {}
        self._token = token
        self._expires = time.monotonic() + float(auth.get("expires_in") or 3600)
        self.user_id = user.get("userID", "")
        self.region = user.get("botRegion") or "us"

    async def call(
        self, path: str, body: dict[str, Any], *, request_id_in_body: bool = False
    ) -> dict[str, Any]:
        """POST to the app API, logging in again once if the token is rejected."""
        for attempt in range(2):
            if self._token is None or time.monotonic() > self._expires - TOKEN_MARGIN:
                await self.login()
            request_id = str(uuid.uuid4())
            status, data = await self._post(
                f"{API_HOST.format(region=self.region)}/{path}",
                {**body, "requestID": request_id} if request_id_in_body else body,
                {
                    "authorization": self._token or "",
                    "RequestID": request_id,
                    "UserID": self.user_id,
                },
            )
            if status in HTTP_UNAUTHORIZED and attempt == 0:
                self._token = None
                continue
            if status >= 400:  # noqa: PLR2004
                msg = f"HTTP {status}: {data.get('message') or 'error'}"
                raise SwitchBotApiError(msg)
            code = data.get("statusCode", data.get("resultCode"))
            if code != STATUS_OK:
                msg = f"{data.get('message') or 'request rejected'} (code {code})"
                raise SwitchBotApiError(msg)
            return data
        msg = "token rejected after logging in again"
        raise SwitchBotAuthError(msg)

    async def get_devices(self) -> list[Device]:
        """Return all devices on the account."""
        data = await self.call("wonder/device/v3/getdevice", {"required_type": "All"})
        return [
            Device(
                mac=item["device_mac"],
                name=(item.get("device_name") or item["device_mac"]).strip(),
                device_type=(item.get("device_detail") or {}).get("device_type", ""),
                group_id=item.get("groupID", ""),
            )
            for item in (data.get("body") or {}).get("Items") or []
        ]

    async def get_effects(self, mac: str, group_id: str, action: str) -> list[Effect]:
        """Return the preset effects followed by the user's own effects."""
        data = await self.call(
            "wonder/devicestatus/v1/userExternal",
            {
                "deviceMac": compact_mac(mac),
                "groupID": group_id,
                "action": action,
                "version": "V1",
            },
        )
        result = (data.get("body") or {}).get("result") or []
        ordered = sorted(result, key=lambda e: (e.get("type", 0), e.get("index", 0)))
        effects: list[Effect] = []
        seen: set[str] = set()
        for item in ordered:
            name = str(item.get("name") or "").strip()
            colors = tuple(int(c) for c in item.get("color") or [])
            if not name or name in seen or not colors:
                continue
            seen.add(name)
            effects.append(Effect(name, int(item["mode"]), colors))
        return effects

    async def invoke(self, mac: str, service: int, params: dict[str, Any]) -> None:
        """Call one thing-model service on a device."""
        await self.call(
            "command/cmd/api/v1/func/invoke",
            {
                "deviceID": compact_mac(mac),
                "functionID": service,
                "params": params,
                "optSrc": "app",
                "timeout": 10000,
            },
            request_id_in_body=True,
        )


class Lamp:
    """One lamp: the account, its model profile and its MAC."""

    def __init__(self, account: SwitchBotAccount, model: LampModel, mac: str) -> None:
        """Bind the account to one device."""
        self.account = account
        self.model = model
        self.mac = mac

    async def get_effects(self, group_id: str) -> list[Effect]:
        """Return the effects available for this lamp."""
        return await self.account.get_effects(
            self.mac, group_id, self.model.effect_list_action
        )

    async def start_effect(self, effect: Effect, speed: int) -> None:
        """Start an effect on the color light at the given speed."""
        await self.account.invoke(self.mac, self.model.set_effect, effect.params())
        await self.set_speed(speed)

    async def set_speed(self, speed: int) -> None:
        """Set the effect speed within the model's range."""
        speed = max(self.model.speed_min, min(self.model.speed_max, speed))
        await self.account.invoke(self.mac, self.model.set_speed, {"0": speed})

    async def set_color_brightness(self, brightness: int) -> None:
        """Set the color light brightness, 1-100 %."""
        brightness = max(1, min(100, brightness))
        await self.account.invoke(
            self.mac, self.model.set_brightness, {"0": brightness}
        )

    async def turn_off_color_light(self) -> None:
        """Turn the color light off and leave the main white light as it is."""
        await self.account.invoke(
            self.mac, self.model.set_power, self.model.color_off_params
        )
