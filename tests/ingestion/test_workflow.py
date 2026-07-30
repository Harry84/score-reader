from db.migrate_runner import apply_schema
from ingestion.workflow import start_ingestion


def _make_ref_team(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute("INSERT INTO ref_teams (name) VALUES (%s) RETURNING id", (name,))
        return cur.fetchone()[0]


def _make_ref_player(pg_conn, name, primary_team_id, primary_role):
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ref_players (name, primary_team_id, primary_role) VALUES (%s, %s, %s) RETURNING id",
            (name, primary_team_id, primary_role),
        )
        return cur.fetchone()[0]


def _get_system_id(pg_conn, name="Zavian Abyss"):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id FROM systems WHERE name = %s", (name,))
        return cur.fetchone()[0]


def _player(name, position, score, kills, deaths, assists, ai_kills, cap_ship_damage):
    return {
        "position": position,
        "player": name,
        "score": score,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "ai_kills": ai_kills,
        "cap_ship_damage": cap_ship_damage,
    }


def test_unambiguous_screenshot_is_persisted_immediately(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    imperial_team_id = _make_ref_team(pg_conn, "181st")
    rebel_team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    _make_ref_player(pg_conn, "Vader", imperial_team_id, "Flex")
    _make_ref_player(pg_conn, "Tarkin", imperial_team_id, "Support")
    _make_ref_player(pg_conn, "Wedge", rebel_team_id, "Flex")
    _make_ref_player(pg_conn, "Luke", rebel_team_id, "Support")
    pg_conn.commit()

    system_id = _get_system_id(pg_conn)

    extracted_data = {
        "match_result": "IMPERIAL VICTORY",
        "teams": {
            "imperial": {
                "players": [
                    _player("Vader", "Titan One", 1675, 4, 2, 1, 18, 30139),
                    _player("Tarkin", "Titan Two", 900, 1, 3, 2, 5, 0),
                ]
            },
            "rebel": {
                "players": [
                    _player("Wedge", "Vanguard One", 1200, 2, 4, 0, 10, 0),
                    _player("Luke", "Vanguard Two", 1400, 3, 1, 2, 12, 0),
                ]
            },
        },
    }

    result = start_ingestion(
        pg_conn,
        turn_id="turn-1",
        system_id=system_id,
        match_type="team",
        screenshot_ref="discord://message/123",
        extracted_data=extracted_data,
    )

    assert result["status"] == "persisted"
    match_id = result["match_id"]

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT winner, match_type, turn_id, system_id, imperial_team_id, rebel_team_id
            FROM matches WHERE id = %s
            """,
            (match_id,),
        )
        winner, match_type, turn_id, row_system_id, row_imp_team, row_reb_team = cur.fetchone()

    assert winner == "IMPERIAL VICTORY"
    assert match_type == "team"
    assert turn_id == "turn-1"
    assert row_system_id == system_id
    assert row_imp_team == imperial_team_id
    assert row_reb_team == rebel_team_id

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT player_name, faction, role, score, kills, is_subbing
            FROM player_stats ps
            WHERE ps.match_id = %s
            ORDER BY player_name
            """,
            (match_id,),
        )
        rows = cur.fetchall()

    assert rows == [
        ("Luke", "REBEL", "Support", 1400, 3, False),
        ("Tarkin", "IMPERIAL", "Support", 900, 1, False),
        ("Vader", "IMPERIAL", "Flex", 1675, 4, False),
        ("Wedge", "REBEL", "Flex", 1200, 2, False),
    ]
