from db.migrate_runner import apply_schema


def test_create_team_then_list_and_get(pg_conn, client):
    apply_schema(pg_conn)
    pg_conn.commit()

    response = client.post("/teams", json={"name": "Rogue Squadron"})
    assert response.status_code == 200
    team = response.json()
    assert team["name"] == "Rogue Squadron"

    listed = client.get("/teams").json()
    assert [t["name"] for t in listed] == ["Rogue Squadron"]

    fetched = client.get(f"/teams/{team['id']}").json()
    assert fetched["id"] == team["id"]


def test_get_nonexistent_team_returns_404(pg_conn, client):
    apply_schema(pg_conn)
    pg_conn.commit()

    response = client.get("/teams/999999")
    assert response.status_code == 404


def test_create_player_then_captain_attaches_to_roster(pg_conn, client):
    apply_schema(pg_conn)
    pg_conn.commit()

    team = client.post("/teams", json={"name": "Rogue Squadron"}).json()
    client.post(f"/teams/{team['id']}/captain", json={"captain_discord_id": "discord-user-1"})
    player = client.post("/players", json={"name": "Wedge"}).json()

    response = client.post(
        f"/teams/{team['id']}/roster",
        json={"requesting_discord_id": "discord-user-1", "ref_player_id": player["id"]},
    )

    assert response.status_code == 200
    with pg_conn.cursor() as cur:
        cur.execute("SELECT primary_team_id FROM ref_players WHERE id = %s", (player["id"],))
        (primary_team_id,) = cur.fetchone()
    assert primary_team_id == team["id"]


def test_non_captain_attach_returns_403(pg_conn, client):
    apply_schema(pg_conn)
    pg_conn.commit()

    team = client.post("/teams", json={"name": "Rogue Squadron"}).json()
    client.post(f"/teams/{team['id']}/captain", json={"captain_discord_id": "discord-user-1"})
    player = client.post("/players", json={"name": "Wedge"}).json()

    response = client.post(
        f"/teams/{team['id']}/roster",
        json={"requesting_discord_id": "someone-else", "ref_player_id": player["id"]},
    )

    assert response.status_code == 403
