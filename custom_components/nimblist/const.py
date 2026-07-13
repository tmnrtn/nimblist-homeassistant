"""Constants for the Nimblist integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "nimblist"

# Config-entry keys
CONF_BASE_URL: Final = "base_url"
CONF_API_TOKEN: Final = "api_token"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_EXPIRY_WINDOW_DAYS: Final = "expiry_window_days"

# Defaults
DEFAULT_BASE_URL: Final = "https://nimblist.app"
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
MIN_SCAN_INTERVAL: Final = 10  # seconds
# "Expiring soon" window: a pantry item counts as expiring when its EstimatedUseBy
# is within this many days of now. It's an estimate, not food-safety advice.
DEFAULT_EXPIRY_WINDOW_DAYS: Final = 7
MIN_EXPIRY_WINDOW_DAYS: Final = 1
MAX_EXPIRY_WINDOW_DAYS: Final = 90

# API
API_KEY_HEADER: Final = "X-Api-Key"
