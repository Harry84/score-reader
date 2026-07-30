import pytest

from db.migrate_runner import apply_schema
from stats.team_elo import recompute_team_elo


def _make_team(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute("INSERT INTO teams (name) VALUES (%s) RETURNING id", (name,))
        return cur.fetchone()[0]


def _make_match(
    pg_conn, imperial_team_id, rebel_team_id, winner, match_date, campaign_id="campaign-1"
):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO matches (imperial_team_id, rebel_team_id, winner, match_type, campaign_id, turn_id, match_date)
            VALUES (%s, %s, %s, 'team', %s, 'turn-1', %s)
            RETURNING id
            """,
            (imperial_team_id, rebel_team_id, winner, campaign_id, match_date),
        )
        return cur.fetchone()[0]


def test_recompute_team_elo_replays_matches_chronologically(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    team_a = _make_team(pg_conn, "Team A")
    team_b = _make_team(pg_conn, "Team B")
    match1_id = _make_match(pg_conn, team_a, team_b, "IMPERIAL", "2026-01-01 12:00:00")
    match2_id = _make_match(pg_conn, team_a, team_b, "REBEL", "2026-01-02 12:00:00")
    pg_conn.commit()

    recompute_team_elo(pg_conn, "campaign-1")

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT rating, matches_played, matches_won, matches_lost, rank FROM team_elo_ratings WHERE team_id = %s",
            (team_a,),
        )
        a_rating, a_played, a_won, a_lost, a_rank = cur.fetchone()
        a_rating = float(a_rating)
        cur.execute(
            "SELECT rating, matches_played, matches_won, matches_lost, rank FROM team_elo_ratings WHERE team_id = %s",
            (team_b,),
        )
        b_rating, b_played, b_won, b_lost, b_rank = cur.fetchone()
        b_rating = float(b_rating)

    # Independently hand-computed (not via calculate_expected_outcome/calculate_new_rating):
    # match 1: both start at 1000, A (imperial) wins -> A=1016.0, B=984.0
    # match 2: same matchup at 1016.0/984.0, B (rebel) wins -> A~=998.5305, B~=1001.4695
    assert a_rating == pytest.approx(998.5305, abs=1e-3)
    assert b_rating == pytest.approx(1001.4695, abs=1e-3)
    assert (a_played, a_won, a_lost) == (2, 1, 1)
    assert (b_played, b_won, b_lost) == (2, 1, 1)
    assert b_rank == 1
    assert a_rank == 2

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT match_id, imperial_old_rating, imperial_new_rating, rebel_old_rating, rebel_new_rating, winner
            FROM team_elo_history ORDER BY match_id
            """
        )
        history = [
            (row[0], float(row[1]), float(row[2]), float(row[3]), float(row[4]), row[5])
            for row in cur.fetchall()
        ]

    assert len(history) == 2
    assert history[0][0] == match1_id
    assert history[0][1] == pytest.approx(1000.0)
    assert history[0][2] == pytest.approx(1016.0)
    assert history[0][3] == pytest.approx(1000.0)
    assert history[0][4] == pytest.approx(984.0)
    assert history[0][5] == "IMPERIAL"

    assert history[1][0] == match2_id
    assert history[1][1] == pytest.approx(1016.0)
    assert history[1][2] == pytest.approx(998.5305, abs=1e-3)
    assert history[1][3] == pytest.approx(984.0)
    assert history[1][4] == pytest.approx(1001.4695, abs=1e-3)
    assert history[1][5] == "REBEL"


def test_recompute_team_elo_starts_teams_with_no_matches_at_starting_elo(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    idle_team = _make_team(pg_conn, "Idle Team")
    pg_conn.commit()

    recompute_team_elo(pg_conn, "campaign-1")

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT rating, matches_played FROM team_elo_ratings WHERE team_id = %s",
            (idle_team,),
        )
        rating, played = cur.fetchone()
        rating = float(rating)

    assert rating == pytest.approx(1000.0)
    assert played == 0


def test_elo_is_isolated_per_campaign(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    team_a = _make_team(pg_conn, "Team A")
    team_b = _make_team(pg_conn, "Team B")
    # Same two (global) teams, but in two separate campaigns with opposite
    # results - each campaign should compute its own independent ladder from
    # its own starting ELO, not share state with the other.
    _make_match(
        pg_conn, team_a, team_b, "IMPERIAL", "2026-01-01 12:00:00", campaign_id="campaign-A"
    )
    _make_match(
        pg_conn, team_a, team_b, "REBEL", "2026-02-01 12:00:00", campaign_id="campaign-B"
    )
    pg_conn.commit()

    recompute_team_elo(pg_conn, "campaign-A")
    recompute_team_elo(pg_conn, "campaign-B")

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT rating FROM team_elo_ratings WHERE team_id = %s AND campaign_id = %s",
            (team_a, "campaign-A"),
        )
        (rating_a_in_a,) = cur.fetchone()
        cur.execute(
            "SELECT rating FROM team_elo_ratings WHERE team_id = %s AND campaign_id = %s",
            (team_a, "campaign-B"),
        )
        (rating_a_in_b,) = cur.fetchone()

    # A won in campaign-A (both started at 1000 -> A=1016), lost in
    # campaign-B (both started at 1000 there too, independently -> A=984).
    # If campaigns leaked into each other, campaign-B's match would replay
    # on top of campaign-A's 1016 instead of a fresh 1000.
    assert float(rating_a_in_a) == pytest.approx(1016.0)
    assert float(rating_a_in_b) == pytest.approx(984.0)

    # Recomputing campaign-B must not touch campaign-A's already-written rows.
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM team_elo_ratings WHERE campaign_id = %s", ("campaign-A",)
        )
        (count_a,) = cur.fetchone()
    assert count_a == 2
