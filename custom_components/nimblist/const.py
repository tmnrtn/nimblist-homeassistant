"""Constants for the Nimblist integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "nimblist"

# Config-entry keys
CONF_BASE_URL: Final = "base_url"
CONF_API_TOKEN: Final = "api_token"
CONF_SCAN_INTERVAL: Final = "scan_interval"

# Defaults
DEFAULT_BASE_URL: Final = "https://nimblist.app"
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
MIN_SCAN_INTERVAL: Final = 10  # seconds

# API
API_KEY_HEADER: Final = "X-Api-Key"
