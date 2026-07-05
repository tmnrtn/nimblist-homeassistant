"""Tests for the Nimblist config flow."""

from __future__ import annotations

import aiohttp
from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nimblist.const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

BASE = "https://nimblist.test"
USERINFO_URL = f"{BASE}/api/auth/userinfo"


async def test_user_flow_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(USERINFO_URL, json={"userId": "u1", "email": "a@b.c"})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_good"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "a@b.c"
    assert result["data"] == {CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_good"}
    assert result["result"].unique_id == "u1"


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(USERINFO_URL, status=401)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_bad"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(USERINFO_URL, exc=aiohttp.ClientError())

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_x"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_rejects_malformed_url(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # No scheme → invalid; caught before any network call (#1126).
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: "nimblist.app", CONF_API_TOKEN: "nbl_x"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}


async def test_user_flow_rejects_http_non_loopback(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # Plain http to a remote host would send the token in the clear (#1126).
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: "http://nimblist.app", CONF_API_TOKEN: "nbl_x"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "insecure_url"}


async def test_user_flow_allows_http_localhost(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # A LAN/self-host over http://localhost is a legitimate Community-Edition config.
    aioclient_mock.get(
        "http://localhost:8080/api/auth/userinfo", json={"userId": "u1", "email": "a@b.c"}
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_BASE_URL: "http://localhost:8080", CONF_API_TOKEN: "nbl_good"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_cannot_connect_when_userinfo_lacks_userid(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # A 200 that isn't a Nimblist userinfo payload must not crash on info["userId"] (#1125).
    aioclient_mock.get(USERINFO_URL, json={"unexpected": True})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_good"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="u1").add_to_hass(hass)
    aioclient_mock.get(USERINFO_URL, json={"userId": "u1", "email": "a@b.c"})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_good"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_success_updates_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u1",
        data={CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_old"},
    )
    entry.add_to_hass(hass)
    aioclient_mock.get(USERINFO_URL, json={"userId": "u1", "email": "a@b.c"})

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "nbl_new"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_TOKEN] == "nbl_new"


async def test_reauth_account_mismatch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u1",
        data={CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_old"},
    )
    entry.add_to_hass(hass)
    # Token resolves to a DIFFERENT account.
    aioclient_mock.get(USERINFO_URL, json={"userId": "u2", "email": "other@b.c"})

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "nbl_other"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_account_mismatch"
    assert entry.data[CONF_API_TOKEN] == "nbl_old"  # unchanged


async def test_options_flow_sets_scan_interval(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="u1",
        data={CONF_BASE_URL: BASE, CONF_API_TOKEN: "nbl_old"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 60
