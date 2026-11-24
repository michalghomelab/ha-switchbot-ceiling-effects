"""Config flow: SwitchBot account login, then pick a supported lamp."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_NAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import Device, SwitchBotAccount, SwitchBotApiError, SwitchBotAuthError
from .const import CONF_DEVICE_TYPE, CONF_GROUP_ID, DOMAIN
from .models import MODELS

if TYPE_CHECKING:
    from collections.abc import Mapping

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL)
        ),
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)


class CeilingEffectsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._credentials: dict[str, str] = {}
        self._lamps: dict[str, Device] = {}

    async def _login(
        self, email: str, password: str
    ) -> tuple[list[Device], dict[str, str]]:
        """Log in and list the supported lamps; return (lamps, errors)."""
        account = SwitchBotAccount(async_get_clientsession(self.hass), email, password)
        try:
            devices = await account.get_devices()
        except SwitchBotAuthError:
            return [], {"base": "invalid_auth"}
        except SwitchBotApiError:
            return [], {"base": "cannot_connect"}
        return [d for d in devices if d.device_type in MODELS], {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the SwitchBot account e-mail and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            lamps, errors = await self._login(email, user_input[CONF_PASSWORD])
            if not errors:
                self._credentials = {
                    CONF_EMAIL: email,
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                }
                configured = self._async_current_ids()
                self._lamps = {
                    lamp.mac: lamp for lamp in lamps if lamp.mac not in configured
                }
                if not self._lamps:
                    return self.async_abort(reason="no_devices")
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the lamp; skipped when there is only one."""
        if user_input is None and len(self._lamps) > 1:
            names = {mac: lamp.name for mac, lamp in self._lamps.items()}
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema({vol.Required(CONF_DEVICE_ID): vol.In(names)}),
            )

        mac = user_input[CONF_DEVICE_ID] if user_input else next(iter(self._lamps))
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()
        lamp = self._lamps[mac]
        return self.async_create_entry(
            title=lamp.name,
            data={
                **self._credentials,
                CONF_DEVICE_ID: mac,
                CONF_DEVICE_TYPE: lamp.device_type,
                CONF_GROUP_ID: lamp.group_id,
                CONF_NAME: lamp.name,
            },
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],  # noqa: ARG002
    ) -> ConfigFlowResult:
        """Start re-authentication after the password was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            _, errors = await self._login(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
