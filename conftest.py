"""Pytest configuration for the Nimblist Home Assistant integration tests."""

from __future__ import annotations

import pytest

# Provided by pytest-homeassistant-custom-component.
pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading `custom_components.nimblist` in every test."""
    yield
