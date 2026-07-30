import pytest

from db.migrate_runner import apply_schema
from teams.onboarding import (
    attach_player_to_roster,
    create_player,
    create_team,
    get_team,
    list_teams,
    set_captain,
)


def test_create_team_is_idempotent_by_name(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    first = create_team(pg_conn, "Rogue Squadron")
    second = create_team(pg_conn, "Rogue Squadron")

    assert first["id"] == second["id"]
    assert first["name"] == "Rogue Squadron"

    with pg_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ref_teams WHERE name = 'Rogue Squadron'")
        (count,) = cur.fetchone()
    assert count == 1


def test_create_player_creates_new_canonical_player(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    team = create_team(pg_conn, "Rogue Squadron")
    player = create_player(pg_conn, "Wedge", primary_team_id=team["id"], primary_role="Flex")

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT name, primary_team_id, primary_role FROM ref_players WHERE id = %s",
            (player["id"],),
        )
        row = cur.fetchone()

    assert row == ("Wedge", team["id"], "Flex")


def test_set_captain_assigns_discord_id_to_team(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    team = create_team(pg_conn, "Rogue Squadron")
    updated = set_captain(pg_conn, team["id"], "discord-user-1")

    assert updated["captain_discord_id"] == "discord-user-1"
    assert get_team(pg_conn, team["id"])["captain_discord_id"] == "discord-user-1"


def test_captain_can_attach_existing_player_to_their_team(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    team = create_team(pg_conn, "Rogue Squadron")
    set_captain(pg_conn, team["id"], "discord-user-1")
    player = create_player(pg_conn, "Wedge")

    attach_player_to_roster(pg_conn, team["id"], "discord-user-1", player["id"])

    with pg_conn.cursor() as cur:
        cur.execute("SELECT primary_team_id FROM ref_players WHERE id = %s", (player["id"],))
        (primary_team_id,) = cur.fetchone()
    assert primary_team_id == team["id"]


def test_non_captain_cannot_attach_player_to_roster(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    team = create_team(pg_conn, "Rogue Squadron")
    set_captain(pg_conn, team["id"], "discord-user-1")
    player = create_player(pg_conn, "Wedge")

    with pytest.raises(PermissionError):
        attach_player_to_roster(pg_conn, team["id"], "someone-else", player["id"])

    with pg_conn.cursor() as cur:
        cur.execute("SELECT primary_team_id FROM ref_players WHERE id = %s", (player["id"],))
        (primary_team_id,) = cur.fetchone()
    assert primary_team_id is None


def test_list_teams_returns_all_teams_alphabetically(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    create_team(pg_conn, "Rogue Squadron")
    create_team(pg_conn, "181st")

    names = [t["name"] for t in list_teams(pg_conn)]
    assert names == ["181st", "Rogue Squadron"]


def test_attach_player_to_nonexistent_team_raises(pg_conn):
    apply_schema(pg_conn)
    pg_conn.commit()

    player = create_player(pg_conn, "Wedge")

    with pytest.raises(ValueError):
        attach_player_to_roster(pg_conn, 999999, "discord-user-1", player["id"])
