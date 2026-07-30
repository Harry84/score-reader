import sqlite3

from db.migrate_runner import apply_schema
from db.sqlite_migration import migrate
from stats_reader.modules.database_utils import create_database
from stats_reader.reference_manager import ReferenceDatabase


def _build_fixture_databases(tmp_path):
    ref_path = str(tmp_path / "ref.db")
    stats_path = str(tmp_path / "stats.db")

    ref_db = ReferenceDatabase(ref_path)
    team_id = ref_db.add_team("Rogue Squadron")
    player_id = ref_db.add_player("Wedge", primary_team_id=team_id, primary_role="Flex")
    ref_db.close()

    create_database(stats_path)
    conn = sqlite3.connect(stats_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO seasons (id, name) VALUES (1, 'SCL15')")
    cur.execute(
        "INSERT INTO teams (id, name, reference_id, wins, losses) VALUES (1, 'Rogue Squadron', ?, 3, 1)",
        (team_id,),
    )
    cur.execute(
        "INSERT INTO teams (id, name, reference_id, wins, losses) VALUES (2, '181st', NULL, 1, 3)"
    )
    cur.execute(
        """
        INSERT INTO matches (id, season_id, match_date, imperial_team_id, rebel_team_id, winner, filename, match_type)
        VALUES (1, 1, '2026-01-05 20:00:00', 2, 1, 'REBEL VICTORY', 'match1.png', 'team')
        """
    )
    cur.execute(
        "INSERT INTO players (id, name, reference_id, player_hash) VALUES (1, 'Wedge', ?, 'hash-wedge')",
        (player_id,),
    )
    cur.execute(
        """
        INSERT INTO player_stats
            (id, match_id, player_id, player_name, player_hash, team_id, faction, position, role,
             score, kills, deaths, assists, ai_kills, cap_ship_damage, is_subbing)
        VALUES (1, 1, 1, 'Wedge', 'hash-wedge', 1, 'REBEL', 'Vanguard One', 'Flex',
                1675, 4, 2, 1, 18, 0, 0)
        """
    )
    conn.commit()
    conn.close()

    return ref_path, stats_path


def test_migrate_copies_reference_and_stats_data_into_postgres(pg_conn, tmp_path):
    apply_schema(pg_conn)
    ref_path, stats_path = _build_fixture_databases(tmp_path)

    counts = migrate(ref_path, stats_path, pg_conn)

    assert counts == {
        "ref_teams": 1,
        "ref_players": 1,
        "seasons": 1,
        "teams": 2,
        "matches": 1,
        "players": 1,
        "player_stats": 1,
    }

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.winner, m.filename, m.match_type, imp.name, reb.name
            FROM matches m
            JOIN teams imp ON m.imperial_team_id = imp.id
            JOIN teams reb ON m.rebel_team_id = reb.id
            WHERE m.id = 1
            """
        )
        winner, filename, match_type, imperial_name, rebel_name = cur.fetchone()

    assert winner == "REBEL VICTORY"
    assert filename == "match1.png"
    assert match_type == "team"
    assert imperial_name == "181st"
    assert rebel_name == "Rogue Squadron"

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT score, kills, deaths, ai_kills, is_subbing FROM player_stats WHERE id = 1"
        )
        score, kills, deaths, ai_kills, is_subbing = cur.fetchone()

    assert (score, kills, deaths, ai_kills, is_subbing) == (1675, 4, 2, 18, False)
