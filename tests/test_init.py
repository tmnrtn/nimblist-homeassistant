"""Scaffold smoke tests for the Nimblist integration."""

from __future__ import annotations

import json
from pathlib import Path

# Importing the package runs __init__.py (which imports Home Assistant),
# so this catches import/scaffold errors at collection time.
import custom_components.nimblist  # noqa: F401
from custom_components.nimblist.const import DEFAULT_BASE_URL, DOMAIN

_MANIFEST = Path(custom_components.nimblist.__file__).parent / "manifest.json"


def test_domain_constant() -> None:
    assert DOMAIN == "nimblist"
    assert DEFAULT_BASE_URL.startswith("https://")


def test_manifest_matches_domain() -> None:
    manifest = json.loads(_MANIFEST.read_text())
    assert manifest["domain"] == DOMAIN
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "cloud_polling"
