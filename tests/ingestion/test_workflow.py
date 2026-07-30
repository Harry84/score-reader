import pytest

from db.migrate_runner import apply_schema
from ingestion.workflow import start_ingestion, submit_answer


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
        campaign_id="campaign-1",
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

    assert winner == "IMPERIAL"
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

    with pg_conn.cursor() as cur:
        cur.execute("SELECT wins, losses FROM teams WHERE id = %s", (row_imp_team,))
        assert cur.fetchone() == (1, 0)
        cur.execute("SELECT wins, losses FROM teams WHERE id = %s", (row_reb_team,))
        assert cur.fetchone() == (0, 1)

    # ELO recompute fires synchronously as part of persist (both start at 1000).
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT rating FROM team_elo_ratings WHERE team_id = %s", (row_imp_team,)
        )
        (imp_rating,) = cur.fetchone()
        cur.execute(
            "SELECT rating FROM team_elo_ratings WHERE team_id = %s", (row_reb_team,)
        )
        (reb_rating,) = cur.fetchone()

    assert float(imp_rating) == pytest.approx(1016.0)
    assert float(reb_rating) == pytest.approx(984.0)


def test_unrecognized_player_name_pauses_for_clarification(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    imperial_team_id = _make_ref_team(pg_conn, "181st")
    rebel_team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    vader_id = _make_ref_player(pg_conn, "Vader", imperial_team_id, "Flex")
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
                    # Typo'd relative to the reference DB's "Vader".
                    _player("Vadar", "Titan One", 1675, 4, 2, 1, 18, 30139),
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
        campaign_id="campaign-1",
        turn_id="turn-1",
        system_id=system_id,
        match_type="team",
        screenshot_ref="discord://message/456",
        extracted_data=extracted_data,
    )

    assert result["status"] == "awaiting_player_match:Vadar"
    assert result["question"] == {
        "type": "player_match",
        "player_name": "Vadar",
        "candidates": [{"id": vader_id, "name": "Vader"}],
    }

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM pending_matches WHERE id = %s",
            (result["pending_match_id"],),
        )
        assert cur.fetchone()[0] == "awaiting_player_match:Vadar"


def test_submit_answer_resolves_paused_player_and_persists_match(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    imperial_team_id = _make_ref_team(pg_conn, "181st")
    rebel_team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    vader_id = _make_ref_player(pg_conn, "Vader", imperial_team_id, "Flex")
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
                    _player("Vadar", "Titan One", 1675, 4, 2, 1, 18, 30139),
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

    paused = start_ingestion(
        pg_conn,
        campaign_id="campaign-1",
        turn_id="turn-1",
        system_id=system_id,
        match_type="team",
        screenshot_ref="discord://message/789",
        extracted_data=extracted_data,
    )
    assert paused["status"] == "awaiting_player_match:Vadar"

    result = submit_answer(
        pg_conn, paused["pending_match_id"], {"ref_player_id": vader_id}
    )

    assert result["status"] == "persisted"
    match_id = result["match_id"]

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT player_name, faction, role, score, is_subbing FROM player_stats WHERE match_id = %s AND player_name = 'Vadar'",
            (match_id,),
        )
        row = cur.fetchone()

    assert row == ("Vadar", "IMPERIAL", "Flex", 1675, False)

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM pending_matches WHERE id = %s",
            (paused["pending_match_id"],),
        )
        assert cur.fetchone()[0] == "persisted"


def test_minority_player_is_auto_flagged_as_subbing_without_a_pause(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    imperial_team_id = _make_ref_team(pg_conn, "181st")
    death_squadron_id = _make_ref_team(pg_conn, "Death Squadron")
    rebel_team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    _make_ref_player(pg_conn, "Vader", imperial_team_id, "Flex")
    _make_ref_player(pg_conn, "Tarkin", imperial_team_id, "Support")
    # Piett's primary team is Death Squadron, but he's subbing for 181st here.
    _make_ref_player(pg_conn, "Piett", death_squadron_id, "Farmer")
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
                    _player("Piett", "Titan Three", 800, 0, 1, 3, 2, 0),
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
        campaign_id="campaign-1",
        turn_id="turn-1",
        system_id=system_id,
        match_type="team",
        screenshot_ref="discord://message/101",
        extracted_data=extracted_data,
    )

    assert result["status"] == "persisted"

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT imperial_team_id FROM matches WHERE id = %s", (result["match_id"],)
        )
        (match_imperial_team_id,) = cur.fetchone()
        cur.execute("SELECT id FROM teams WHERE reference_id = %s", (imperial_team_id,))
        (expected_team_row_id,) = cur.fetchone()

    assert match_imperial_team_id == expected_team_row_id

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT player_name, is_subbing FROM player_stats WHERE match_id = %s ORDER BY player_name",
            (result["match_id"],),
        )
        rows = cur.fetchall()

    assert rows == [
        ("Luke", False),
        ("Piett", True),
        ("Tarkin", False),
        ("Vader", False),
        ("Wedge", False),
    ]


def test_no_clear_majority_pauses_for_team_assignment(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    team_a_id = _make_ref_team(pg_conn, "181st")
    team_b_id = _make_ref_team(pg_conn, "Death Squadron")
    rebel_team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    # A genuine 2-2 tie: no faction majority to infer from.
    _make_ref_player(pg_conn, "Vader", team_a_id, "Flex")
    _make_ref_player(pg_conn, "Tarkin", team_b_id, "Support")
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

    paused = start_ingestion(
        pg_conn,
        campaign_id="campaign-1",
        turn_id="turn-1",
        system_id=system_id,
        match_type="team",
        screenshot_ref="discord://message/202",
        extracted_data=extracted_data,
    )

    assert paused["status"] == "awaiting_team_assignment:imperial"
    assert paused["question"]["type"] == "team_assignment"
    assert paused["question"]["faction"] == "imperial"
    assert {c["id"] for c in paused["question"]["candidates"]} == {team_a_id, team_b_id}

    result = submit_answer(
        pg_conn, paused["pending_match_id"], {"ref_team_id": team_a_id}
    )

    assert result["status"] == "persisted"

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT player_name, is_subbing FROM player_stats WHERE match_id = %s ORDER BY player_name",
            (result["match_id"],),
        )
        rows = cur.fetchall()

    assert rows == [
        ("Luke", False),
        ("Tarkin", True),
        ("Vader", False),
        ("Wedge", False),
    ]


def test_player_with_no_primary_role_pauses_for_clarification(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    imperial_team_id = _make_ref_team(pg_conn, "181st")
    rebel_team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    _make_ref_player(pg_conn, "Vader", imperial_team_id, None)
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

    paused = start_ingestion(
        pg_conn,
        campaign_id="campaign-1",
        turn_id="turn-1",
        system_id=system_id,
        match_type="team",
        screenshot_ref="discord://message/303",
        extracted_data=extracted_data,
    )

    assert paused["status"] == "awaiting_role:Vader"
    assert paused["question"] == {
        "type": "role",
        "player_name": "Vader",
        "candidates": ["Farmer", "Flex", "Support"],
    }

    result = submit_answer(pg_conn, paused["pending_match_id"], {"role": "Flex"})

    assert result["status"] == "persisted"

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT role FROM player_stats WHERE match_id = %s AND player_name = 'Vader'",
            (result["match_id"],),
        )
        assert cur.fetchone()[0] == "Flex"


def test_pickup_match_uses_generic_teams_and_nulls_player_team_id(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    # Different primary teams on the same faction - would pause for
    # match_type "team" (no clear majority), but pickup never assigns
    # players to a team at all, so this should persist directly.
    team_a_id = _make_ref_team(pg_conn, "181st")
    team_b_id = _make_ref_team(pg_conn, "Death Squadron")
    rebel_team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    _make_ref_player(pg_conn, "Vader", team_a_id, "Flex")
    _make_ref_player(pg_conn, "Tarkin", team_b_id, "Support")
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
        campaign_id="campaign-1",
        turn_id="turn-1",
        system_id=system_id,
        match_type="pickup",
        screenshot_ref="discord://message/909",
        extracted_data=extracted_data,
    )

    assert result["status"] == "persisted"
    match_id = result["match_id"]

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT imp.name, reb.name FROM matches m
            JOIN teams imp ON m.imperial_team_id = imp.id
            JOIN teams reb ON m.rebel_team_id = reb.id
            WHERE m.id = %s
            """,
            (match_id,),
        )
        imperial_team_name, rebel_team_name = cur.fetchone()

    assert imperial_team_name == "Imp_pickup_team"
    assert rebel_team_name == "NR_pickup_team"

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT player_name, team_id, is_subbing FROM player_stats WHERE match_id = %s ORDER BY player_name",
            (match_id,),
        )
        rows = cur.fetchall()

    assert rows == [
        ("Luke", None, False),
        ("Tarkin", None, False),
        ("Vader", None, False),
        ("Wedge", None, False),
    ]

    # Player ELO recompute fires synchronously for pickup, same as team ELO
    # does for match_type "team" (both sides started at 1000, imperial won).
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.name, per.rating FROM player_elo_ratings per
            JOIN players p ON per.player_id = p.id
            WHERE per.campaign_id = 'campaign-1' AND per.match_type = 'pickup' AND per.role = 'general'
            ORDER BY p.name
            """
        )
        general_ratings = {name: float(rating) for name, rating in cur.fetchall()}

    assert general_ratings["Vader"] == pytest.approx(1016.0)
    assert general_ratings["Wedge"] == pytest.approx(984.0)


def test_ranked_match_uses_generic_ranked_team_names(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    imperial_team_id = _make_ref_team(pg_conn, "181st")
    rebel_team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    _make_ref_player(pg_conn, "Vader", imperial_team_id, "Flex")
    _make_ref_player(pg_conn, "Wedge", rebel_team_id, "Flex")
    pg_conn.commit()

    system_id = _get_system_id(pg_conn)

    extracted_data = {
        "match_result": "REBEL VICTORY",
        "teams": {
            "imperial": {"players": [_player("Vader", "Titan One", 1000, 2, 2, 0, 5, 0)]},
            "rebel": {"players": [_player("Wedge", "Vanguard One", 1500, 5, 0, 1, 10, 0)]},
        },
    }

    result = start_ingestion(
        pg_conn,
        campaign_id="campaign-1",
        turn_id="turn-1",
        system_id=system_id,
        match_type="ranked",
        screenshot_ref="discord://message/910",
        extracted_data=extracted_data,
    )

    assert result["status"] == "persisted"

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT imp.name, reb.name FROM matches m
            JOIN teams imp ON m.imperial_team_id = imp.id
            JOIN teams reb ON m.rebel_team_id = reb.id
            WHERE m.id = %s
            """,
            (result["match_id"],),
        )
        imperial_team_name, rebel_team_name = cur.fetchone()

    assert imperial_team_name == "Imperial_ranked_team"
    assert rebel_team_name == "NR_ranked_team"

    # Ranked gets its own player ELO ladder too (REBEL won here).
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.name, per.rating FROM player_elo_ratings per
            JOIN players p ON per.player_id = p.id
            WHERE per.campaign_id = 'campaign-1' AND per.match_type = 'ranked' AND per.role = 'general'
            ORDER BY p.name
            """
        )
        general_ratings = {name: float(rating) for name, rating in cur.fetchall()}

    assert general_ratings["Vader"] == pytest.approx(984.0)
    assert general_ratings["Wedge"] == pytest.approx(1016.0)
