"""Applies plain-SQL migration files under db/migrations/ to a Postgres connection."""

import os

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def apply_schema(conn):
    """Apply any not-yet-applied migration file, in filename order."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute("SELECT filename FROM schema_migrations")
        applied = {row[0] for row in cur.fetchall()}
    conn.commit()

    for filename in sorted(os.listdir(MIGRATIONS_DIR)):
        if not filename.endswith(".sql") or filename in applied:
            continue
        with open(os.path.join(MIGRATIONS_DIR, filename), "r", encoding="utf-8") as f:
            sql = f.read()
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)", (filename,)
            )
        conn.commit()
