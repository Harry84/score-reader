import pytest
from fastapi.testclient import TestClient

from api import config
from api.main import app, get_pg_conn


@pytest.fixture
def client(pg_conn):
    app.dependency_overrides[get_pg_conn] = lambda: pg_conn
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def campaign_headers():
    """X-API-Key header for the campaign-facing read endpoints
    (ROADMAP Phase 5) - api/config.py: CAMPAIGN_API_KEY."""
    return {"X-API-Key": config.CAMPAIGN_API_KEY}
