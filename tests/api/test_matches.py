from unittest.mock import patch

from db.migrate_runner import apply_schema


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


def _unambiguous_extracted_data():
    return {
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


@patch("api.main.extract_from_image_bytes")
def test_post_matches_extracts_and_persists_unambiguous_screenshot(
    mock_extract, pg_conn, client
):
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
    mock_extract.return_value = _unambiguous_extracted_data()

    response = client.post(
        "/matches",
        data={
            "campaign_id": "campaign-1",
            "turn_id": "turn-1",
            "system_id": str(system_id),
            "match_type": "team",
            "screenshot_ref": "discord://message/123",
        },
        files={"image": ("screenshot.png", b"fake-screenshot-bytes", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "persisted"
    assert "match_id" in body
    mock_extract.assert_called_once()
    assert mock_extract.call_args.args[0] == b"fake-screenshot-bytes"


@patch("api.main.extract_from_image_bytes")
def test_post_matches_answer_resumes_a_paused_workflow(mock_extract, pg_conn, client):
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

    extracted_data = _unambiguous_extracted_data()
    extracted_data["teams"]["imperial"]["players"][0]["player"] = "Vadar"
    mock_extract.return_value = extracted_data

    start_response = client.post(
        "/matches",
        data={
            "campaign_id": "campaign-1",
            "turn_id": "turn-1",
            "system_id": str(system_id),
            "match_type": "team",
            "screenshot_ref": "discord://message/456",
        },
        files={"image": ("screenshot.png", b"fake-screenshot-bytes", "image/png")},
    )

    assert start_response.status_code == 200
    paused = start_response.json()
    assert paused["status"] == "awaiting_player_match:Vadar"

    answer_response = client.post(
        f"/matches/{paused['pending_match_id']}/answer",
        json={"answer": {"ref_player_id": vader_id}},
    )

    assert answer_response.status_code == 200
    body = answer_response.json()
    assert body["status"] == "persisted"
    assert "match_id" in body
