import pytest

from db.migrate_runner import apply_schema
from stats.player_elo import recompute_player_elo


def _make_player(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO players (name, player_hash) VALUES (%s, %s) RETURNING id",
            (name, name),
        )
        return cur.fetchone()[0]


def _make_match(pg_conn, match_type, campaign_id, winner, match_date):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO matches (winner, match_type, campaign_id, turn_id, match_date)
            VALUES (%s, %s, %s, 'turn-1', %s)
            RETURNING id
            """,
            (winner, match_type, campaign_id, match_date),
        )
        return cur.fetchone()[0]


def _make_player_stat(pg_conn, match_id, player_id, faction, role):
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO player_stats (match_id, player_id, faction, role) VALUES (%s, %s, %s, %s)",
            (match_id, player_id, faction, role),
        )


def _rating(pg_conn, player_id, campaign_id, match_type, role):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT rating, matches_played, matches_won, matches_lost, rank
            FROM player_elo_ratings
            WHERE player_id = %s AND campaign_id = %s AND match_type = %s AND role = %s
            """,
            (player_id, campaign_id, match_type, role),
        )
        row = cur.fetchone()
    if row is None:
        return None
    rating, played, won, lost, rank = row
    return (float(rating), played, won, lost, rank)


def test_recompute_player_elo_computes_general_and_role_ladders(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    p1 = _make_player(pg_conn, "Player1")
    p2 = _make_player(pg_conn, "Player2")
    match_id = _make_match(pg_conn, "pickup", "campaign-1", "IMPERIAL", "2026-01-01 12:00:00")
    _make_player_stat(pg_conn, match_id, p1, "IMPERIAL", "Flex")
    _make_player_stat(pg_conn, match_id, p2, "REBEL", "Support")
    pg_conn.commit()

    recompute_player_elo(pg_conn, "campaign-1", "pickup")

    # Independently hand-computed (same formula as the team ELO test):
    # both start at 1000, imperial (p1) wins -> p1=1016.0, p2=984.0.
    assert _rating(pg_conn, p1, "campaign-1", "pickup", "general") == (1016.0, 1, 1, 0, 1)
    assert _rating(pg_conn, p1, "campaign-1", "pickup", "Flex") == (1016.0, 1, 1, 0, 1)
    assert _rating(pg_conn, p2, "campaign-1", "pickup", "general") == (984.0, 1, 0, 1, 2)
    assert _rating(pg_conn, p2, "campaign-1", "pickup", "Support") == (984.0, 1, 0, 1, 1)

    # Nobody played Farmer - no rows for it at all.
    assert _rating(pg_conn, p1, "campaign-1", "pickup", "Farmer") is None
    assert _rating(pg_conn, p2, "campaign-1", "pickup", "Farmer") is None


def test_role_ladders_only_include_players_who_played_that_role(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    p1 = _make_player(pg_conn, "Player1")
    p2 = _make_player(pg_conn, "Player2")
    p3 = _make_player(pg_conn, "Player3")
    p4 = _make_player(pg_conn, "Player4")

    match1 = _make_match(pg_conn, "pickup", "campaign-1", "IMPERIAL", "2026-01-01 12:00:00")
    _make_player_stat(pg_conn, match1, p1, "IMPERIAL", "Flex")
    _make_player_stat(pg_conn, match1, p2, "REBEL", "Support")

    match2 = _make_match(pg_conn, "pickup", "campaign-1", "REBEL", "2026-01-02 12:00:00")
    _make_player_stat(pg_conn, match2, p3, "IMPERIAL", "Farmer")
    _make_player_stat(pg_conn, match2, p4, "REBEL", "Support")
    pg_conn.commit()

    recompute_player_elo(pg_conn, "campaign-1", "pickup")

    # Each match is an independent 1000-vs-1000 case (different players).
    assert _rating(pg_conn, p1, "campaign-1", "pickup", "Flex") == (1016.0, 1, 1, 0, 1)
    assert _rating(pg_conn, p3, "campaign-1", "pickup", "Farmer") == (984.0, 1, 0, 1, 1)
    assert _rating(pg_conn, p4, "campaign-1", "pickup", "Support") == (1016.0, 1, 1, 0, 1)
    assert _rating(pg_conn, p2, "campaign-1", "pickup", "Support") == (984.0, 1, 0, 1, 2)

    # Flex ladder never mentions p2/p3/p4; Farmer ladder never mentions p1/p2/p4.
    assert _rating(pg_conn, p2, "campaign-1", "pickup", "Flex") is None
    assert _rating(pg_conn, p3, "campaign-1", "pickup", "Flex") is None
    assert _rating(pg_conn, p4, "campaign-1", "pickup", "Flex") is None
    assert _rating(pg_conn, p1, "campaign-1", "pickup", "Farmer") is None
    assert _rating(pg_conn, p2, "campaign-1", "pickup", "Farmer") is None
    assert _rating(pg_conn, p4, "campaign-1", "pickup", "Farmer") is None

    # General ladder includes all four.
    for pid in (p1, p2, p3, p4):
        assert _rating(pg_conn, pid, "campaign-1", "pickup", "general") is not None


def test_player_elo_is_isolated_per_campaign_and_match_type(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    p1 = _make_player(pg_conn, "Player1")
    p2 = _make_player(pg_conn, "Player2")

    pickup_match = _make_match(pg_conn, "pickup", "campaign-A", "IMPERIAL", "2026-01-01 12:00:00")
    _make_player_stat(pg_conn, pickup_match, p1, "IMPERIAL", "Flex")
    _make_player_stat(pg_conn, pickup_match, p2, "REBEL", "Support")

    ranked_match = _make_match(pg_conn, "ranked", "campaign-A", "REBEL", "2026-01-02 12:00:00")
    _make_player_stat(pg_conn, ranked_match, p1, "IMPERIAL", "Flex")
    _make_player_stat(pg_conn, ranked_match, p2, "REBEL", "Support")
    pg_conn.commit()

    recompute_player_elo(pg_conn, "campaign-A", "pickup")
    recompute_player_elo(pg_conn, "campaign-A", "ranked")

    # Same player, same campaign, but pickup and ranked are wholly separate
    # ladders - each computed fresh from starting ELO, not chained together.
    pickup_rating, *_ = _rating(pg_conn, p1, "campaign-A", "pickup", "general")
    ranked_rating, *_ = _rating(pg_conn, p1, "campaign-A", "ranked", "general")
    assert pickup_rating == pytest.approx(1016.0)
    assert ranked_rating == pytest.approx(984.0)
