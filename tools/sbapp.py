#!/usr/bin/env python3
"""
Explore the private SwitchBot app API to add support for another lamp.

Standard library only. See docs/adding-a-lamp.md for the full walkthrough.

    sbapp.py login                      log in (asks for e-mail and password)
    sbapp.py devices                    list devices with their device_type
    sbapp.py plugins                    list app panel plugins and download URLs
    sbapp.py effects MAC GROUP_ID [ACTION]
                                        list effects (default getColorfulEffect)
    sbapp.py shadow MAC ID [ID ...]     read thing-model properties (read-only)
    sbapp.py invoke MAC SERVICE JSON    call a thing-model service (changes the lamp!)

The session token (not the password) is saved to .sbapp_session.json in the
current directory, readable only by you. It expires after about two hours.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

CLIENT_ID = "5nnwmhmsa9xxskm14hd85lm9bm"
ACCOUNT = "https://account.api.switchbot.net/account/api/v1/user"
PUBLISH = "https://publish.api.switchbot.net/publishplatform/api/v1/rn/plugin"
SESSION = ".sbapp_session.json"
# The plugin list depends on the app version; use a recent one.
APP_VERSION = "10.11"


def post(url: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        sys.exit(f"HTTP {err.code}: {err.read().decode()[:300]}")


def session() -> dict[str, str]:
    try:
        with open(SESSION) as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit("Run `sbapp.py login` first.")


def app_call(path: str, body: dict[str, Any], request_id: str | None = None) -> Any:
    s = session()
    request_id = request_id or str(uuid.uuid4())
    return post(
        f"https://wonderlabs.{s['region']}.api.switchbot.net/{path}",
        body,
        {"authorization": s["token"], "RequestID": request_id, "UserID": s["user_id"]},
    )


def show(data: Any) -> None:
    print(json.dumps(data, indent=1, ensure_ascii=False))


def cmd_login() -> None:
    email = input("SwitchBot e-mail: ").strip()
    password = getpass.getpass("Password: ")
    login = post(
        f"{ACCOUNT}/login",
        {
            "clientId": CLIENT_ID,
            "username": email,
            "password": password,
            "grantType": "password",
            "verifyCode": "",
        },
    )
    if login.get("statusCode") != 100:
        sys.exit(f"Login failed: {login.get('statusCode')} {login.get('message')}")
    token = login["body"]["access_token"]
    user = post(f"{ACCOUNT}/userinfo", {}, {"authorization": token}).get("body", {})
    fd = os.open(SESSION, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(
            {
                "token": token,
                "user_id": user.get("userID", ""),
                "region": user.get("botRegion") or "us",
            },
            f,
        )
    print(f"OK, region {user.get('botRegion')}; token saved to {SESSION}")


def cmd_devices() -> None:
    data = app_call("wonder/device/v3/getdevice", {"required_type": "All"})
    for item in data.get("body", {}).get("Items", []):
        detail = item.get("device_detail") or {}
        print(
            f"{item['device_mac']}  type={detail.get('device_type')}  "
            f"group={item.get('groupID')}  name={item.get('device_name', '').strip()}"
        )


def cmd_plugins() -> None:
    data = post(
        PUBLISH,
        {
            "platform": "android",
            "appVersion": APP_VERSION,
            "userID": session()["user_id"],
        },
        {"authorization": session()["token"]},
    )
    for plugin in data.get("body", {}).get("rnList", []):
        print(f"{plugin['rnName']:<22} {plugin['downloadUrl']}")


def cmd_effects(mac: str, group_id: str, action: str = "getColorfulEffect") -> None:
    show(
        app_call(
            "wonder/devicestatus/v1/userExternal",
            {"deviceMac": mac, "groupID": group_id, "action": action, "version": "V1"},
        )
    )


def cmd_shadow(mac: str, *ids: str) -> None:
    data = app_call(
        "device/device/v1/shadow/getByIDs",
        {"deviceID": mac, "propertyIDs": [int(i) for i in ids]},
    )
    for key, prop in (data.get("data") or {}).items():
        print(f"{key}: {prop.get('value')}")


def cmd_invoke(mac: str, service: str, params: str) -> None:
    request_id = str(uuid.uuid4())
    show(
        app_call(
            "command/cmd/api/v1/func/invoke",
            {
                "deviceID": mac,
                "functionID": int(service),
                "params": json.loads(params),
                "optSrc": "app",
                "timeout": 10000,
                "requestID": request_id,
            },
            request_id,
        )
    )


COMMANDS = {
    "login": cmd_login,
    "devices": cmd_devices,
    "plugins": cmd_plugins,
    "effects": cmd_effects,
    "shadow": cmd_shadow,
    "invoke": cmd_invoke,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    try:
        COMMANDS[sys.argv[1]](*sys.argv[2:])
    except TypeError:
        sys.exit(__doc__)
