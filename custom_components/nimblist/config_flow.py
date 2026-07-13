"""Config flow for the Nimblist integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

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
    CONF_EXPIRY_WINDOW_DAYS,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_EXPIRY_WINDOW_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_EXPIRY_WINDOW_DAYS,
    MIN_EXPIRY_WINDOW_DAYS,
    MIN_SCAN_INTERVAL,
)


# Hosts for which a plain-http Server URL is acceptable (a LAN self-host is a legitimate
# Community-Edition config); anywhere else, http would send the API token in cleartext (#1126).
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _normalise_base_url(raw: str) -> tuple[str | None, str | None]:
    """Validate + normalise the Server URL. Returns (url, None) or (None, error_code).

    Rejects anything that isn't a well-formed http/https URL, and blocks ``http://`` for
    non-loopback hosts so the ``X-Api-Key`` token can't be sent in cleartext (#1126).
    """
    base = (raw or "").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None, "invalid_url"
    if parsed.scheme == "http" and parsed.hostname.lower() not in _LOOPBACK_HOSTS:
        return None, "insecure_url"
    return base, None


async def _validate(hass, base_url: str, token: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return (userinfo, None) on success or (None, error_code) on failure."""
    client = NimblistApiClient(base_url, token, async_get_clientsession(hass))
    try:
        info = await client.async_validate()
    except NimblistAuthError:
        return None, "invalid_auth"
    except NimblistConnectionError:
        return None, "cannot_connect"
    # A 200 without a userId (204, or a non-Nimblist server behind the URL) must not crash on
    # info["userId"] later — surface it as a connection problem (#1125).
    if not info or not info.get("userId"):
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
            base_url, url_error = _normalise_base_url(user_input[CONF_BASE_URL])
            if url_error:
                errors["base"] = url_error
            else:
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
        """Manage the update interval and pantry expiry window."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_window = self.config_entry.options.get(
            CONF_EXPIRY_WINDOW_DAYS, DEFAULT_EXPIRY_WINDOW_DAYS
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                ),
                vol.Optional(
                    CONF_EXPIRY_WINDOW_DAYS, default=current_window
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_EXPIRY_WINDOW_DAYS, max=MAX_EXPIRY_WINDOW_DAYS),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
