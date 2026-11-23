"""Config flow: token + secret, then pick an RGBICWW Ceiling Light."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE_ID, CONF_NAME, CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import SwitchBotApi, SwitchBotApiError, SwitchBotAuthError
from .const import CONF_SECRET, DEVICE_TYPE, DOMAIN

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): TextSelector(),
        vol.Required(CONF_SECRET): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class CeilingEffectsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._credentials: dict[str, str] = {}
        self._devices: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the API token and secret."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api = SwitchBotApi(
                async_get_clientsession(self.hass),
                user_input[CONF_TOKEN].strip(),
                user_input[CONF_SECRET].strip(),
            )
            try:
                devices = await api.get_devices()
            except SwitchBotAuthError:
                errors["base"] = "invalid_auth"
            except SwitchBotApiError:
                errors["base"] = "cannot_connect"
            else:
                self._credentials = {
                    CONF_TOKEN: user_input[CONF_TOKEN].strip(),
                    CONF_SECRET: user_input[CONF_SECRET].strip(),
                }
                configured = self._async_current_ids()
                self._devices = {
                    d["deviceId"]: d.get("deviceName") or d["deviceId"]
                    for d in devices
                    if d.get("deviceType") == DEVICE_TYPE
                    and d["deviceId"] not in configured
                }
                if not self._devices:
                    return self.async_abort(reason="no_devices")
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the lamp; skipped when there is only one."""
        if user_input is None and len(self._devices) > 1:
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema(
                    {vol.Required(CONF_DEVICE_ID): vol.In(self._devices)}
                ),
            )

        device_id = (
            user_input[CONF_DEVICE_ID] if user_input else next(iter(self._devices))
        )
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()
        name = self._devices[device_id]
        return self.async_create_entry(
            title=name,
            data={**self._credentials, CONF_DEVICE_ID: device_id, CONF_NAME: name},
        )
