from db.migrate_runner import apply_schema


def _make_ref_team(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute("INSERT INTO ref_teams (name) VALUES (%s) RETURNING id", (name,))
        return cur.fetchone()[0]


def _make_ref_player(pg_conn, name, primary_team_id):
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ref_players (name, primary_team_id) VALUES (%s, %s) RETURNING id",
            (name, primary_team_id),
        )
        return cur.fetchone()[0]


def _make_team(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute("INSERT INTO teams (name) VALUES (%s) RETURNING id", (name,))
        return cur.fetchone()[0]


def _make_player(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute("INSERT INTO players (name) VALUES (%s) RETURNING id", (name,))
        return cur.fetchone()[0]


def _make_match(pg_conn, imperial_team_id, rebel_team_id, winner, campaign_id, turn_id, system_id, match_type="team"):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO matches (imperial_team_id, rebel_team_id, winner, match_type, campaign_id, turn_id, system_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (imperial_team_id, rebel_team_id, winner, match_type, campaign_id, turn_id, system_id),
        )
        return cur.fetchone()[0]


def _get_system_id(pg_conn, name="Zavian Abyss"):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id FROM systems WHERE name = %s", (name,))
        return cur.fetchone()[0]


def test_reads_require_campaign_api_key(pg_conn, client):
    apply_schema(pg_conn)
    pg_conn.commit()

    team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    pg_conn.commit()

    routes = [
        f"/teams/{team_id}/roster",
        "/matches/latest?campaign_id=c&turn_id=t&system_id=1",
        "/elo/teams?campaign_id=c",
        "/elo/players?campaign_id=c&match_type=pickup",
    ]
    for route in routes:
        assert client.get(route).status_code == 401
        assert client.get(route, headers={"X-API-Key": "wrong"}).status_code == 401


def test_get_team_roster(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()

    team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    _make_ref_player(pg_conn, "Wedge", team_id)
    _make_ref_player(pg_conn, "Luke", team_id)
    _make_ref_player(pg_conn, "Vader", None)
    pg_conn.commit()

    response = client.get(f"/teams/{team_id}/roster", headers=campaign_headers)

    assert response.status_code == 200
    assert [p["name"] for p in response.json()] == ["Luke", "Wedge"]


def test_get_team_roster_nonexistent_team_returns_404(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()

    response = client.get("/teams/999999/roster", headers=campaign_headers)

    assert response.status_code == 404


def test_get_latest_match(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()

    imperial_id = _make_team(pg_conn, "181st")
    rebel_id = _make_team(pg_conn, "Rogue Squadron")
    system_id = _get_system_id(pg_conn)
    _make_match(pg_conn, imperial_id, rebel_id, "IMPERIAL", "campaign-1", "turn-1", system_id)
    latest_id = _make_match(pg_conn, imperial_id, rebel_id, "REBEL", "campaign-1", "turn-1", system_id)
    pg_conn.commit()

    response = client.get(
        "/matches/latest",
        params={"campaign_id": "campaign-1", "turn_id": "turn-1", "system_id": system_id},
        headers=campaign_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["match_id"] == latest_id
    assert body["winner"] == "REBEL"
    assert body["campaign_id"] == "campaign-1"
    assert body["turn_id"] == "turn-1"
    assert body["system_id"] == system_id


def test_get_latest_match_none_found_returns_404(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()

    response = client.get(
        "/matches/latest",
        params={"campaign_id": "no-such-campaign", "turn_id": "turn-1", "system_id": 1},
        headers=campaign_headers,
    )

    assert response.status_code == 404


def test_get_team_elo_ladder(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()

    team_id = _make_team(pg_conn, "181st")
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO team_elo_ratings (team_id, campaign_id, rating, matches_played, matches_won, matches_lost, rank)
            VALUES (%s, 'campaign-1', 1016.0, 1, 1, 0, 1)
            """,
            (team_id,),
        )
    pg_conn.commit()

    response = client.get("/elo/teams", params={"campaign_id": "campaign-1"}, headers=campaign_headers)

    assert response.status_code == 200
    ladder = response.json()
    assert ladder == [
        {
            "team_id": team_id,
            "name": "181st",
            "rating": 1016.0,
            "matches_played": 1,
            "matches_won": 1,
            "matches_lost": 0,
            "rank": 1,
        }
    ]


def test_get_player_elo_ladder(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()

    player_id = _make_player(pg_conn, "Wedge")
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO player_elo_ratings (player_id, campaign_id, match_type, role, rating, matches_played, matches_won, matches_lost, rank)
            VALUES (%s, 'campaign-1', 'pickup', 'general', 1016.0, 1, 1, 0, 1)
            """,
            (player_id,),
        )
    pg_conn.commit()

    response = client.get(
        "/elo/players",
        params={"campaign_id": "campaign-1", "match_type": "pickup"},
        headers=campaign_headers,
    )

    assert response.status_code == 200
    ladder = response.json()
    assert ladder == [
        {
            "player_id": player_id,
            "name": "Wedge",
            "rating": 1016.0,
            "matches_played": 1,
            "matches_won": 1,
            "matches_lost": 0,
            "rank": 1,
        }
    ]
