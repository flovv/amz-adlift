"""Pytest configuration enabling deterministic local dev test mode unless overridden."""

import pytest


@pytest.fixture(autouse=True)
def _enable_dev_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMZ_FLYWHEEL_DEV_TEST_MODE", "1")
