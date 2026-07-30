import pytest
from fastapi.testclient import TestClient

from api.main import app, get_pg_conn


@pytest.fixture
def client(pg_conn):
    app.dependency_overrides[get_pg_conn] = lambda: pg_conn
    yield TestClient(app)
    app.dependency_overrides.clear()
