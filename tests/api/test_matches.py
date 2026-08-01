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


def _confirm_roster_sizes(client, result):
    """Fixtures here use abbreviated <5-a-side rosters; confirm past the
    roster_size validation pause(s) via the HTTP answer endpoint before
    exercising whatever the test actually cares about."""
    while result["status"].startswith("awaiting_roster_size:"):
        response = client.post(
            f"/matches/{result['pending_match_id']}/answer",
            json={"answer": {"confirm": True}},
        )
        result = response.json()
    return result


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
    body = _confirm_roster_sizes(client, response.json())
    assert body["status"] == "persisted"
    assert "match_id" in body
    mock_extract.assert_called_once()
    assert mock_extract.call_args.args[0] == b"fake-screenshot-bytes"


@patch("api.main.extract_from_image_bytes")
def test_post_matches_rejects_duplicate_image_without_calling_claude(mock_extract, pg_conn, client):
    """Reposting the exact same image bytes should be rejected by the cheap
    pre-extraction image-hash check (ingestion.workflow.check_duplicate_image)
    before extract_from_image_bytes (the paid Claude call) ever runs again."""
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

    def post_screenshot(screenshot_ref):
        return client.post(
            "/matches",
            data={
                "campaign_id": "campaign-1",
                "turn_id": "turn-1",
                "system_id": str(system_id),
                "match_type": "team",
                "screenshot_ref": screenshot_ref,
            },
            files={"image": ("screenshot.png", b"fake-screenshot-bytes", "image/png")},
        )

    first = post_screenshot("discord://message/first")
    assert first.status_code == 200
    first_body = _confirm_roster_sizes(client, first.json())
    assert first_body["status"] == "persisted"
    assert mock_extract.call_count == 1

    second = post_screenshot("discord://message/second")

    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["message"] == (
        f"Match already entered as match {first_body['match_id']} "
        "(this exact screenshot was already uploaded)"
    )
    assert detail["existing_match"]["match_id"] == first_body["match_id"]
    # The whole point of the pre-extraction check: no second Claude call.
    assert mock_extract.call_count == 1


@patch("api.main.extract_from_image_bytes")
def test_post_matches_rejects_same_stats_from_a_different_image_with_409(mock_extract, pg_conn, client):
    """A *different* image that happens to extract to identical stats should
    still be caught, just by the later stats-hash check (extraction has to
    run first here, since the images themselves differ)."""
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

    def post_screenshot(screenshot_ref, image_bytes):
        return client.post(
            "/matches",
            data={
                "campaign_id": "campaign-1",
                "turn_id": "turn-1",
                "system_id": str(system_id),
                "match_type": "team",
                "screenshot_ref": screenshot_ref,
            },
            files={"image": ("screenshot.png", image_bytes, "image/png")},
        )

    first = post_screenshot("discord://message/first", b"first-screenshot-bytes")
    assert first.status_code == 200
    first_body = _confirm_roster_sizes(client, first.json())
    assert first_body["status"] == "persisted"

    second = post_screenshot("discord://message/second", b"a-visibly-different-screenshot")

    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["message"] == (
        f"Match already entered as match {first_body['match_id']} "
        "(the same stats were already recorded from a different screenshot)"
    )
    assert detail["existing_match"]["match_id"] == first_body["match_id"]
    # Extraction *did* run the second time - different bytes, so the cheap
    # image-hash check couldn't short-circuit it.
    assert mock_extract.call_count == 2


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
    paused = _confirm_roster_sizes(client, start_response.json())
    assert paused["status"] == "awaiting_player_match:Vadar"

    answer_response = client.post(
        f"/matches/{paused['pending_match_id']}/answer",
        json={"answer": {"ref_player_id": vader_id}},
    )

    assert answer_response.status_code == 200
    body = _confirm_roster_sizes(client, answer_response.json())
    assert body["status"] == "persisted"
    assert "match_id" in body


def _persist_unambiguous_match(mock_extract, pg_conn, client):
    imperial_team_id = _make_ref_team(pg_conn, "181st")
    rebel_team_id = _make_ref_team(pg_conn, "Rogue Squadron")
    _make_ref_player(pg_conn, "Vader", imperial_team_id, "Flex")
    _make_ref_player(pg_conn, "Tarkin", imperial_team_id, "Support")
    _make_ref_player(pg_conn, "Wedge", rebel_team_id, "Flex")
    _make_ref_player(pg_conn, "Luke", rebel_team_id, "Support")
    pg_conn.commit()

    mock_extract.return_value = _unambiguous_extracted_data()
    response = client.post(
        "/matches",
        data={
            "campaign_id": "campaign-1",
            "turn_id": "turn-1",
            "system_id": str(_get_system_id(pg_conn)),
            "match_type": "team",
            "screenshot_ref": "discord://message/edit-test",
        },
        files={"image": ("screenshot.png", b"fake-screenshot-bytes", "image/png")},
    )
    return _confirm_roster_sizes(client, response.json())


@patch("api.main.extract_from_image_bytes")
def test_patch_match_player_updates_stats(mock_extract, pg_conn, client):
    apply_schema(pg_conn)
    pg_conn.commit()

    match = _persist_unambiguous_match(mock_extract, pg_conn, client)

    response = client.patch(
        f"/matches/{match['match_id']}/players/Vader",
        json={"updates": {"score": 2000, "kills": 10}},
    )

    assert response.status_code == 200
    vader = next(p for p in response.json()["players"]["imperial"] if p["player"] == "Vader")
    assert vader["score"] == 2000
    assert vader["kills"] == 10


@patch("api.main.extract_from_image_bytes")
def test_patch_match_player_unknown_player_returns_404(mock_extract, pg_conn, client):
    apply_schema(pg_conn)
    pg_conn.commit()

    match = _persist_unambiguous_match(mock_extract, pg_conn, client)

    response = client.patch(
        f"/matches/{match['match_id']}/players/Nobody",
        json={"updates": {"score": 1}},
    )

    assert response.status_code == 404


@patch("api.main.extract_from_image_bytes")
def test_patch_match_winner_flips_result(mock_extract, pg_conn, client):
    apply_schema(pg_conn)
    pg_conn.commit()

    match = _persist_unambiguous_match(mock_extract, pg_conn, client)
    assert match["winner"] == "IMPERIAL"

    response = client.patch(f"/matches/{match['match_id']}/winner", json={"winner": "REBEL"})

    assert response.status_code == 200
    assert response.json()["winner"] == "REBEL"
