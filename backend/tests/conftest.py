"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires live Postgres / embedding stack",
    )


@pytest.fixture(scope="session")
def db_available() -> bool:
    """True when DATABASE_URL / Postgres is reachable."""
    if os.getenv("SKIP_INTEGRATION_TESTS", "").lower() in ("1", "true", "yes"):
        return False
    try:
        from database.db import Database

        db = Database()
        db.cur.execute("SELECT 1")
        db.close()
        return True
    except Exception:
        return False


@pytest.fixture
def skip_without_db(db_available):
    if not db_available:
        pytest.skip("Postgres not available — set DATABASE_URL or skip integration tests")
