import os

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv()

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://squadrons:squadrons@localhost:5433/squadrons_test",
)


def _drop_all_tables(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = [row[0] for row in cur.fetchall()]
        for table in tables:
            cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    conn.commit()


@pytest.fixture
def pg_conn():
    """A connection to a Postgres test database, wiped clean before each test."""
    conn = psycopg2.connect(TEST_DATABASE_URL)
    _drop_all_tables(conn)
    yield conn
    conn.close()
