"""
Shared test fixtures.

Why this exists: the panel's auth is driven by the `PANEL_PASSWORD` env var. If a
developer happens to have it exported in their shell, every existing API test
suddenly gets a 401 and the suite looks broken. Individual test files were each
rolling their own `TestClient`, so the behaviour depended on the ambient env.

This conftest makes the default deterministic: unless a test opts in, auth is OFF.
Tests that DO want the lock use the `locked` fixture in test_auth.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsa_wrap import api


@pytest.fixture(autouse=True)
def _auth_off_by_default(monkeypatch):
    """Auth is off unless a test asks for it."""
    monkeypatch.delenv("PANEL_PASSWORD", raising=False)
    monkeypatch.delenv("PANEL_SECRET", raising=False)


@pytest.fixture
def client():
    """A plain, unauthenticated client with auth forced off."""
    with TestClient(api.app) as c:
        yield c
