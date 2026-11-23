"""Minimal client for the SwitchBot Cloud API v1.1."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from typing import Any

import aiohttp

API_URL = "https://api.switch-bot.com/v1.1"
STATUS_OK = 100
TIMEOUT = aiohttp.ClientTimeout(total=10)
HTTP_UNAUTHORIZED = (401, 403)

# https://github.com/OpenWonderLabs/SwitchBotAPI#standard-http-error-codes
STATUS_MESSAGES = {
    151: "device type does not support this command",
    152: "device not found",
    160: "command not supported by this device",
    161: "device offline",
    171: "hub offline",
    190: "device internal error or invalid parameters",
}


class SwitchBotApiError(Exception):
    """Raised when a SwitchBot API call fails."""


class SwitchBotAuthError(SwitchBotApiError):
    """Raised when the token or secret is rejected."""


def sign_headers(
    token: str, secret: str, *, t: str | None = None, nonce: str | None = None
) -> dict[str, str]:
    """Build the HMAC-SHA256 signed headers required by API v1.1."""
    t = t or str(int(time.time() * 1000))
    nonce = nonce or str(uuid.uuid4())
    digest = hmac.new(
        secret.encode(), f"{token}{t}{nonce}".encode(), hashlib.sha256
    ).digest()
    return {
        "Authorization": token,
        "sign": base64.b64encode(digest).decode(),
        "t": t,
        "nonce": nonce,
        "Content-Type": "application/json; charset=utf8",
    }


class SwitchBotApi:
    """Thin async wrapper around the endpoints this integration needs."""

    def __init__(self, session: aiohttp.ClientSession, token: str, secret: str) -> None:
        """Store the session and credentials."""
        self._session = session
        self._token = token
        self._secret = secret

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{API_URL}{path}",
                headers=sign_headers(self._token, self._secret),
                json=payload,
                timeout=TIMEOUT,
            ) as resp:
                if resp.status in HTTP_UNAUTHORIZED:
                    msg = "invalid token or secret"
                    raise SwitchBotAuthError(msg)
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            msg = f"cannot reach SwitchBot API: {err}"
            raise SwitchBotApiError(msg) from err

        status = data.get("statusCode")
        if status != STATUS_OK:
            detail = STATUS_MESSAGES.get(status) or data.get("message") or "unknown"
            msg = f"{detail} (statusCode {status})"
            raise SwitchBotApiError(msg)
        return data.get("body")

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return physical devices on the account."""
        body = await self._request("GET", "/devices")
        return body.get("deviceList", []) if body else []

    async def send_command(
        self, device_id: str, command: str, parameter: Any = "default"
    ) -> None:
        """Send a control command to a device."""
        await self._request(
            "POST",
            f"/devices/{device_id}/commands",
            {"commandType": "command", "command": command, "parameter": parameter},
        )
