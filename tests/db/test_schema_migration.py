from db.migrate_runner import apply_schema


def test_apply_schema_creates_expected_tables(pg_conn):
    apply_schema(pg_conn)

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        tables = {row[0] for row in cur.fetchall()}

    expected = {
        "seasons",
        "teams",
        "matches",
        "players",
        "player_stats",
        "ref_teams",
        "ref_players",
        "systems",
        "pending_matches",
    }
    assert expected.issubset(tables)


def test_systems_table_is_seeded_with_the_eight_known_systems(pg_conn):
    apply_schema(pg_conn)

    with pg_conn.cursor() as cur:
        cur.execute("SELECT name FROM systems ORDER BY name")
        names = {row[0] for row in cur.fetchall()}

    assert names == {
        "Nadiri Dockyards",
        "Esseles",
        "Zavian Abyss",
        "Galitan",
        "Sissubo",
        "Yavin Prime",
        "Fostar Haven",
        "The Maw",
    }
