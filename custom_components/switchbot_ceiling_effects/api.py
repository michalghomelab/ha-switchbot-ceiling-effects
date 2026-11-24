"""
Client for the private SwitchBot app API (the one the SwitchBot app itself uses).

The public Cloud API v1.1 cannot set the effect speed, so everything here goes
through the app's "thing model" services instead. Endpoints and parameters come
from the SwitchBot app (v10.11) and its React Native panel plugins.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import aiohttp

from .models import BLE_KEEP, BLE_OFF, BLE_ON, power_byte

if TYPE_CHECKING:
    from .models import BleProfile, LampModel, Properties

_LOGGER = logging.getLogger(__name__)

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


class SwitchBotBleError(Exception):
    """Raised when a Bluetooth command fails, so the cloud can take over."""


class BleSender(Protocol):
    """Sends raw commands to a lamp over Bluetooth."""

    @property
    def available(self) -> bool:
        """Whether the lamp is in range of a Bluetooth adapter or proxy."""

    async def send(self, commands: list[str]) -> None:
        """Send hex commands in order, or raise SwitchBotBleError."""


@dataclass(frozen=True)
class Device:
    """A device on the SwitchBot account."""

    mac: str
    name: str
    device_type: str
    group_id: str


@dataclass(frozen=True)
class LampState:
    """What the lamp reports to the cloud. A field is None when unknown."""

    white_on: bool | None = None
    white_brightness: int | None = None  # 1-100 %
    white_kelvin: int | None = None
    color_on: bool | None = None
    color_brightness: int | None = None  # 1-100 %
    effect_running: bool | None = None


def state_from_advertisement(data: dict[str, Any], props: Properties) -> LampState:
    """
    Turn one parsed advertisement into the lamp state.

    pySwitchbot names these fields the same way for every light: the color
    sub-light is `isOn`/`brightness`/`color_mode`, the white one `main_*`,
    and `cw` is the white light's color temperature.
    """
    mode = data.get("color_mode")
    return LampState(
        white_on=data.get("main_isOn"),
        white_brightness=data.get("main_brightness"),
        white_kelvin=data.get("cw"),
        color_on=data.get("isOn"),
        color_brightness=data.get("brightness"),
        effect_running=None if mode is None else mode == props.effect_mode,
    )


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

    def ble_packets(self, profile: BleProfile) -> list[str]:
        """Return the effect as Bluetooth packets, colors split across them."""
        colors = [f"{c:06X}" for c in self.colors]
        size = profile.colors_per_packet
        chunks = [colors[i : i + size] for i in range(0, len(colors), size)]
        style_low = self.mode & 0xFF
        style_high_and_count = ((self.mode >> 8 & 0x0F) << 4) | len(colors)
        return [
            profile.effect_packet.format(
                style_low, style_high_and_count, index, "".join(chunk)
            )
            for index, chunk in enumerate(chunks)
        ]


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

    async def get_properties(self, mac: str, ids: list[int]) -> dict[int, Any]:
        """Read thing-model properties the lamp reports to the cloud."""
        data = await self.call(
            "device/device/v1/shadow/getByIDs",
            {"deviceID": compact_mac(mac), "propertyIDs": ids},
        )
        shadow = data.get("data") or {}
        values: dict[int, Any] = {}
        for key, prop in shadow.items():
            value = (prop or {}).get("value")
            if value is not None:
                values[int(key)] = value
        return values

    async def get_ble_key(self, mac: str) -> tuple[str, str]:
        """Fetch the key that lets this account talk to the lamp over Bluetooth."""
        data = await self.call(
            "wonder/keys/v1/communicate",
            {"device_mac": compact_mac(mac), "keyType": "user"},
        )
        key = (data.get("body") or {}).get("communicationKey") or {}
        key_id, encryption_key = key.get("keyId"), key.get("key")
        if not key_id or not encryption_key:
            msg = "the account did not return a Bluetooth key for this lamp"
            raise SwitchBotApiError(msg)
        return str(key_id), str(encryption_key)

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
    """
    One lamp: the account, its model profile and its MAC.

    Commands go over Bluetooth when the lamp is in range of an adapter or
    proxy, and through the cloud otherwise.
    """

    def __init__(
        self,
        account: SwitchBotAccount,
        model: LampModel,
        mac: str,
        ble: BleSender | None = None,
    ) -> None:
        """Bind the account to one device."""
        self.account = account
        self.model = model
        self.mac = mac
        self.ble = ble

    @property
    def ble_in_use(self) -> bool:
        """Whether commands are currently going over Bluetooth."""
        return self.ble is not None and self.ble.available

    async def _send(
        self, service: int, params: dict[str, Any], ble: list[str] | None = None
    ) -> None:
        """Send one command over Bluetooth, falling back to the cloud."""
        if ble and self.ble is not None and self.ble.available:
            try:
                await self.ble.send(ble)
            except SwitchBotBleError as err:
                _LOGGER.debug("Bluetooth failed (%s), using the cloud instead", err)
            else:
                return
        await self.account.invoke(self.mac, service, params)

    async def get_effects(self, group_id: str) -> list[Effect]:
        """Return the effects available for this lamp."""
        return await self.account.get_effects(
            self.mac, group_id, self.model.effect_list_action
        )

    async def get_state(self) -> LampState:
        """Read back what the lamp currently reports."""
        props = self.model.properties
        if props is None:
            return LampState()
        ids = [
            props.white_power,
            props.white_brightness,
            props.white_kelvin,
            props.color_power,
            props.color_brightness,
            props.color_mode,
        ]
        values = await self.account.get_properties(self.mac, ids)

        def flag(prop: int) -> bool | None:
            value = values.get(prop)
            return None if value is None else bool(value)

        def number(prop: int) -> int | None:
            value = values.get(prop)
            return int(value) if isinstance(value, (int, float)) else None

        mode = number(props.color_mode)
        return LampState(
            white_on=flag(props.white_power),
            white_brightness=number(props.white_brightness),
            white_kelvin=number(props.white_kelvin),
            color_on=flag(props.color_power),
            color_brightness=number(props.color_brightness),
            effect_running=None if mode is None else mode == props.effect_mode,
        )

    async def start_effect(self, effect: Effect, speed: int) -> None:
        """Start an effect on the color light at the given speed."""
        ble = self.model.ble
        await self._send(
            self.model.set_effect,
            effect.params(),
            effect.ble_packets(ble) if ble else None,
        )
        await self.set_speed(speed)

    async def set_speed(self, speed: int) -> None:
        """Set the effect speed within the model's range."""
        speed = max(self.model.speed_min, min(self.model.speed_max, speed))
        ble = self.model.ble
        await self._send(
            self.model.set_speed,
            {"0": speed},
            [ble.effect_speed.format(speed)] if ble else None,
        )

    async def set_color_brightness(self, brightness: int) -> None:
        """Set the color light brightness, 1-100 %."""
        brightness = max(1, min(100, brightness))
        ble = self.model.ble
        await self._send(
            self.model.set_brightness,
            {"0": brightness},
            [ble.color_brightness.format(brightness)] if ble else None,
        )

    async def set_white(
        self,
        *,
        on: bool,
        brightness: int | None = None,
        kelvin: int | None = None,
    ) -> None:
        """Switch the main white light; when turning on, optionally set its look."""
        white = self.model.white
        if white is None:
            msg = f"{self.model.name} has no white light"
            raise SwitchBotApiError(msg)
        ble = self.model.ble

        params = white.on_params if on else white.off_params
        state = BLE_ON if on else BLE_OFF
        await self._send(
            self.model.set_power,
            params,
            [ble.power.format(power_byte(white=state, color=BLE_KEEP))]
            if ble
            else None,
        )
        if not on:
            return

        if brightness is not None:
            brightness = max(1, min(100, brightness))
        if kelvin is not None:
            kelvin = max(white.min_kelvin, min(white.max_kelvin, kelvin))

        if brightness is not None and kelvin is not None:
            await self._send(
                white.set_brightness_color_temp,
                {"0": brightness, "1": kelvin},
                [ble.white_brightness_color_temp.format(brightness, kelvin)]
                if ble
                else None,
            )
        elif brightness is not None:
            await self._send(
                white.set_brightness,
                {"0": brightness},
                [ble.white_brightness.format(brightness)] if ble else None,
            )
        elif kelvin is not None:
            await self._send(
                white.set_color_temp,
                {"0": kelvin},
                [ble.white_color_temp.format(kelvin)] if ble else None,
            )

    async def turn_off_color_light(self) -> None:
        """Turn the color light off and leave the main white light as it is."""
        ble = self.model.ble
        await self._send(
            self.model.set_power,
            self.model.color_off_params,
            [ble.power.format(power_byte(white=BLE_KEEP, color=BLE_OFF))]
            if ble
            else None,
        )
