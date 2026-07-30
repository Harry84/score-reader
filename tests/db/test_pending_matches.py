import psycopg2
import pytest

from db.migrate_runner import apply_schema


def _get_system_id(pg_conn, name="Zavian Abyss"):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id FROM systems WHERE name = %s", (name,))
        return cur.fetchone()[0]


def test_pending_match_round_trips_through_full_status_sequence(pg_conn):
    apply_schema(pg_conn)
    system_id = _get_system_id(pg_conn)

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pending_matches (turn_id, system_id, match_type, screenshot_ref, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            ("turn-42", system_id, "team", "discord://message/123", "extracted"),
        )
        pending_match_id = cur.fetchone()[0]
    pg_conn.commit()

    # awaiting_match_type is not in this sequence: match_type is a required
    # ingestion input, not an ambiguous workflow step (ROADMAP Phase 1).
    sequence = [
        "awaiting_player_match:PlayerX",
        "awaiting_subbing:PlayerX",
        "awaiting_role:PlayerX",
        "ready",
        "persisted",
    ]

    for status in sequence:
        with pg_conn.cursor() as cur:
            cur.execute(
                "UPDATE pending_matches SET status = %s WHERE id = %s",
                (status, pending_match_id),
            )
        pg_conn.commit()

        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM pending_matches WHERE id = %s", (pending_match_id,)
            )
            assert cur.fetchone()[0] == status


def test_pending_match_rejects_invalid_status(pg_conn):
    apply_schema(pg_conn)
    system_id = _get_system_id(pg_conn)

    with pytest.raises(psycopg2.errors.CheckViolation):
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pending_matches (turn_id, system_id, match_type, screenshot_ref, status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                ("turn-42", system_id, "team", "discord://message/123", "bogus_status"),
            )
    pg_conn.rollback()
