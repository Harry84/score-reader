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
        "/seasons",
        "/matchups?team_a=NWS&team_b=KE",
        "/matches/1",
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


def _make_season(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute("INSERT INTO seasons (name) VALUES (%s) RETURNING id", (name,))
        return cur.fetchone()[0]


def _set_season(pg_conn, match_id, season_id):
    with pg_conn.cursor() as cur:
        cur.execute("UPDATE matches SET season_id = %s WHERE id = %s", (season_id, match_id))


def _add_stat(pg_conn, match_id, player_id, name, faction, score, team_id):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO player_stats (match_id, player_id, player_name, team_id, faction, role,
                                      score, kills, deaths, assists, ai_kills, cap_ship_damage, is_subbing)
            VALUES (%s, %s, %s, %s, %s, 'dogfighter', %s, 3, 1, 2, 4, 0, false)
            """,
            (match_id, player_id, name, team_id, faction, score),
        )


def test_list_seasons_counts_matches(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()
    s14 = _make_season(pg_conn, "SCL14")
    _make_season(pg_conn, "SCL15")
    a, b = _make_team(pg_conn, "NWS"), _make_team(pg_conn, "KE")
    system_id = _get_system_id(pg_conn)
    _set_season(pg_conn, _make_match(pg_conn, a, b, "IMPERIAL", "c", "t1", system_id), s14)
    pg_conn.commit()

    response = client.get("/seasons", headers=campaign_headers)

    assert response.status_code == 200
    by_name = {s["name"]: s["match_count"] for s in response.json()}
    assert by_name["SCL14"] == 1
    assert by_name["SCL15"] == 0


def test_matchup_counts_wins_from_either_side_and_filters_by_season(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()
    s14, s15 = _make_season(pg_conn, "SCL14"), _make_season(pg_conn, "SCL15")
    a, b, other = _make_team(pg_conn, "NWS"), _make_team(pg_conn, "KE"), _make_team(pg_conn, "RND")
    system_id = _get_system_id(pg_conn)
    m1 = _make_match(pg_conn, a, b, "IMPERIAL", "c", "t1", system_id)   # NWS wins as Imperial
    m2 = _make_match(pg_conn, b, a, "REBEL", "c", "t2", system_id)      # NWS wins as Rebel
    m3 = _make_match(pg_conn, b, a, "IMPERIAL", "c", "t3", system_id)   # KE wins
    _make_match(pg_conn, a, other, "IMPERIAL", "c", "t4", system_id)    # not this matchup
    _set_season(pg_conn, m1, s14)
    _set_season(pg_conn, m2, s15)
    _set_season(pg_conn, m3, s15)
    pg_conn.commit()

    body = client.get("/matchups?team_a=nws&team_b=KE", headers=campaign_headers).json()
    assert (body["team_a"]["name"], body["team_a"]["wins"]) == ("NWS", 2)
    assert (body["team_b"]["name"], body["team_b"]["wins"]) == ("KE", 1)
    assert len(body["matches"]) == 3

    body = client.get(f"/matchups?team_a=NWS&team_b=KE&season_id={s15}", headers=campaign_headers).json()
    assert {m["match_id"] for m in body["matches"]} == {m2, m3}
    assert (body["team_a"]["wins"], body["team_b"]["wins"]) == (1, 1)


def test_matchup_unknown_team_is_404(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()
    _make_team(pg_conn, "NWS")
    pg_conn.commit()

    response = client.get("/matchups?team_a=NWS&team_b=Nobody", headers=campaign_headers)
    assert response.status_code == 404
    assert "Nobody" in response.json()["detail"]


def test_match_detail_returns_scoreboard_by_faction(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()
    a, b = _make_team(pg_conn, "NWS"), _make_team(pg_conn, "KE")
    wedge, vader = _make_player(pg_conn, "Wedge"), _make_player(pg_conn, "Vader")
    system_id = _get_system_id(pg_conn)
    match_id = _make_match(pg_conn, a, b, "REBEL", "c", "t1", system_id)
    _add_stat(pg_conn, match_id, vader, "Vader", "IMPERIAL", 900, a)
    _add_stat(pg_conn, match_id, wedge, "Wedge", "REBEL", 1200, b)
    pg_conn.commit()

    response = client.get(f"/matches/{match_id}", headers=campaign_headers)

    assert response.status_code == 200
    body = response.json()
    assert (body["imperial_team"], body["rebel_team"], body["winner"]) == ("NWS", "KE", "REBEL")
    assert body["players"]["rebel"][0]["player"] == "Wedge"
    assert body["players"]["imperial"][0]["score"] == 900


def test_match_detail_unknown_match_is_404_and_latest_still_routes(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()

    assert client.get("/matches/9999", headers=campaign_headers).status_code == 404
    # /matches/latest must still reach its own route, not /matches/{match_id}
    latest = client.get("/matches/latest?campaign_id=c&turn_id=t&system_id=1", headers=campaign_headers)
    assert latest.status_code == 404
    assert "No match for campaign_id" in latest.json()["detail"]


def _add_role_stat(pg_conn, match_id, player_id, name, faction, role, score, kills, deaths, ai_kills):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO player_stats (match_id, player_id, player_name, faction, role,
                                      score, kills, deaths, assists, ai_kills, cap_ship_damage, is_subbing)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, 0, false)
            """,
            (match_id, player_id, name, faction, role, score, kills, deaths, ai_kills),
        )


def _two_pickups(pg_conn):
    """Wedge wins one as Rebel, then loses one as Imperial; Vader the reverse."""
    system_id = _get_system_id(pg_conn)
    a, b = _make_team(pg_conn, "NWS"), _make_team(pg_conn, "KE")
    wedge, vader = _make_player(pg_conn, "Wedge"), _make_player(pg_conn, "Vader")
    m1 = _make_match(pg_conn, a, b, "REBEL", "campaign-1", "t1", system_id, match_type="pickup")
    m2 = _make_match(pg_conn, a, b, "REBEL", "campaign-1", "t2", system_id, match_type="pickup")
    with pg_conn.cursor() as cur:
        cur.execute("UPDATE matches SET match_date = '2026-01-01' WHERE id = %s", (m1,))
        cur.execute("UPDATE matches SET match_date = '2026-01-02' WHERE id = %s", (m2,))
    _add_role_stat(pg_conn, m1, wedge, "Wedge", "REBEL", "Farmer", 1200, 3, 1, 20)
    _add_role_stat(pg_conn, m1, vader, "Vader", "IMPERIAL", "Flex", 800, 1, 3, 0)
    _add_role_stat(pg_conn, m2, wedge, "Wedge", "IMPERIAL", "Flex", 600, 1, 2, 0)
    _add_role_stat(pg_conn, m2, vader, "Vader", "REBEL", "Flex", 1500, 4, 0, 10)
    return wedge, vader, m1, m2


def test_player_elo_history_is_newest_first_with_the_change(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()
    wedge, _, m1, m2 = _two_pickups(pg_conn)
    with pg_conn.cursor() as cur:
        for match_id, faction, old, new, winner in [(m1, "REBEL", 1000, 1016, "REBEL"),
                                                    (m2, "IMPERIAL", 1016, 1001.5, "REBEL")]:
            cur.execute(
                """
                INSERT INTO player_elo_history (match_id, campaign_id, match_type, role, player_id,
                                                faction, old_rating, new_rating, winner)
                VALUES (%s, 'campaign-1', 'pickup', 'general', %s, %s, %s, %s, %s)
                """,
                (match_id, wedge, faction, old, new, winner),
            )
    pg_conn.commit()

    body = client.get("/elo/players/history",
                      params={"campaign_id": "campaign-1", "player": "wedge", "match_type": "pickup"},
                      headers=campaign_headers).json()

    assert body["player"] == "Wedge"
    assert [(h["match_id"], h["change"], h["won"]) for h in body["history"]] == [(m2, -14.5, False), (m1, 16.0, True)]


def test_player_elo_history_unknown_player_is_404(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()
    response = client.get("/elo/players/history",
                          params={"campaign_id": "c", "player": "Nobody", "match_type": "pickup"},
                          headers=campaign_headers)
    assert response.status_code == 404 and "Nobody" in response.json()["detail"]


def test_player_career_totals_averages_kd_and_roles(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()
    _, _, m1, m2 = _two_pickups(pg_conn)
    pg_conn.commit()

    body = client.get("/players/career", params={"player": "Wedge"}, headers=campaign_headers).json()

    assert (body["matches"], body["wins"], body["losses"]) == (2, 1, 1)
    assert body["totals"]["score"] == 1800 and body["averages"]["score"] == 900.0
    assert body["kd"] == round(4 / 3, 2)
    assert body["by_role"] == {"Farmer": {"matches": 1, "average_score": 1200.0},
                               "Flex": {"matches": 1, "average_score": 600.0}}
    assert [r["match_id"] for r in body["recent"]] == [m2, m1]

    none = client.get("/players/career", params={"player": "Wedge", "match_type": "team"},
                      headers=campaign_headers).json()
    assert none["matches"] == 0 and none["kd"] is None


def test_stat_leaders_rank_by_total_average_kd_and_role(pg_conn, client, campaign_headers):
    apply_schema(pg_conn)
    pg_conn.commit()
    _two_pickups(pg_conn)
    pg_conn.commit()

    def leaders(**params):
        return [(r["player"], r["value"]) for r in client.get(
            "/stats/leaders", params=params, headers=campaign_headers).json()["leaders"]]

    assert leaders(stat="ai_kills") == [("Wedge", 20.0), ("Vader", 10.0)]
    assert leaders(stat="score", per="average") == [("Vader", 1150.0), ("Wedge", 900.0)]
    assert leaders(stat="kd") == [("Vader", round(5 / 3, 2)), ("Wedge", round(4 / 3, 2))]
    assert leaders(stat="score", role="flex") == [("Vader", 2300.0), ("Wedge", 600.0)]
    assert leaders(stat="score", min_matches=3) == []
    assert client.get("/stats/leaders", params={"stat": "nope"}, headers=campaign_headers).status_code == 422
