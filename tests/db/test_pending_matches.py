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
            INSERT INTO pending_matches (campaign_id, turn_id, system_id, match_type, screenshot_ref, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            ("campaign-1", "turn-42", system_id, "team", "discord://message/123", "extracted"),
        )
        pending_match_id = cur.fetchone()[0]
    pg_conn.commit()

    # awaiting_match_type and awaiting_subbing aren't in this sequence: match_type
    # is a required ingestion input, and subbing is auto-computed once team
    # assignment resolves (majority vote or awaiting_team_assignment) - neither
    # ended up needing its own pause (ROADMAP Phase 1). awaiting_role isn't
    # either: a missing role no longer pauses at all (ROADMAP Phase 3 - fixed
    # via edit_match_player instead), and the CHECK constraint was tightened
    # to match (0011_pending_matches_status_validation.sql).
    sequence = [
        "awaiting_player_match:PlayerX",
        "awaiting_team_assignment:imperial",
        "awaiting_roster_size:imperial",
        "awaiting_missing_field:PlayerX:kills",
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
                INSERT INTO pending_matches (campaign_id, turn_id, system_id, match_type, screenshot_ref, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                ("campaign-1", "turn-42", system_id, "team", "discord://message/123", "bogus_status"),
            )
    pg_conn.rollback()
