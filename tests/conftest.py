"""Shared fixtures: load the custom integration from this repo."""
import pytest


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    yield
