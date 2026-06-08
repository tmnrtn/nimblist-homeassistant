"""Config flow for the Nimblist integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NimblistApiClient, NimblistAuthError, NimblistConnectionError
from .const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)


async def _validate(hass, base_url: str, token: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return (userinfo, None) on success or (None, error_code) on failure."""
    client = NimblistApiClient(base_url, token, async_get_clientsession(hass))
    try:
        info = await client.async_validate()
    except NimblistAuthError:
        return None, "invalid_auth"
    except NimblistConnectionError:
        return None, "cannot_connect"
    return info, None


class NimblistConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nimblist."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: server URL + API token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].rstrip("/")
            token = user_input[CONF_API_TOKEN]
            info, error = await _validate(self.hass, base_url, token)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(info["userId"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info.get("email") or "Nimblist",
                    data={CONF_BASE_URL: base_url, CONF_API_TOKEN: token},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                vol.Required(CONF_API_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the token is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt for a fresh API token for the existing account."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            base_url = reauth_entry.data[CONF_BASE_URL]
            token = user_input[CONF_API_TOKEN]
            info, error = await _validate(self.hass, base_url, token)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(info["userId"])
                self._abort_if_unique_id_mismatch(reason="reauth_account_mismatch")
                return self.async_update_reload_and_abort(
                    reauth_entry, data={**reauth_entry.data, CONF_API_TOKEN: token}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NimblistOptionsFlow:
        """Return the options flow."""
        return NimblistOptionsFlow()


class NimblistOptionsFlow(OptionsFlow):
    """Handle Nimblist options (poll interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the update interval."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
