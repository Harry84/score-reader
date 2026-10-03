"""One-time import of the existing SQLite reference/stats databases into Postgres.

Row IDs are preserved during copy (rather than remapped) so the existing
foreign-key relationships between tables carry over unchanged.
"""

import sqlite3

REF_TABLE_COLUMNS = {
    "ref_teams": ["id", "name", "alias"],
    "ref_players": ["id", "name", "primary_team_id", "primary_role", "alias", "source_file"],
}

STATS_TABLE_COLUMNS = {
    "seasons": ["id", "name"],
    "teams": ["id", "name", "reference_id", "wins", "losses"],
    "matches": [
        "id",
        "season_id",
        "match_date",
        "imperial_team_id",
        "rebel_team_id",
        "winner",
        "filename",
        "match_type",
    ],
    "players": ["id", "name", "reference_id", "player_hash"],
    "player_stats": [
        "id",
        "match_id",
        "player_id",
        "player_name",
        "player_hash",
        "team_id",
        "faction",
        "position",
        "role",
        "score",
        "kills",
        "deaths",
        "assists",
        "ai_kills",
        "cap_ship_damage",
        "is_subbing",
    ],
}

# Column-level value transforms applied when copying from SQLite to Postgres,
# for columns whose types don't implicitly convert (e.g. SQLite's 0/1 integer
# into Postgres's BOOLEAN).
COLUMN_TRANSFORMS = {
    "player_stats": {"is_subbing": bool},
}


def migrate(ref_sqlite_path, stats_sqlite_path, pg_conn):
    """Copy ref_teams/ref_players and seasons/teams/matches/players/player_stats
    from the given SQLite database files into pg_conn's database.

    Returns a dict of table name -> number of rows copied.
    """
    counts = {}

    ref_conn = sqlite3.connect(ref_sqlite_path)
    ref_conn.row_factory = sqlite3.Row
    try:
        for table, columns in REF_TABLE_COLUMNS.items():
            counts[table] = _copy_table(ref_conn, pg_conn, table, columns)
    finally:
        ref_conn.close()

    stats_conn = sqlite3.connect(stats_sqlite_path)
    stats_conn.row_factory = sqlite3.Row
    try:
        for table, columns in STATS_TABLE_COLUMNS.items():
            counts[table] = _copy_table(stats_conn, pg_conn, table, columns)
    finally:
        stats_conn.close()

    _reset_sequences(pg_conn, list(REF_TABLE_COLUMNS) + list(STATS_TABLE_COLUMNS))
    pg_conn.commit()

    return counts


def _copy_table(sqlite_conn, pg_conn, table, columns):
    rows = sqlite_conn.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    if not rows:
        return 0

    transforms = COLUMN_TRANSFORMS.get(table, {})
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))

    with pg_conn.cursor() as cur:
        for row in rows:
            values = [
                transforms[col](row[col]) if col in transforms else row[col]
                for col in columns
            ]
            cur.execute(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", values
            )

    return len(rows)


def _reset_sequences(pg_conn, tables):
    # Table names come from our own fixed internal list (never user input), so
    # f-string interpolation of the identifier here is safe.
    with pg_conn.cursor() as cur:
        for table in tables:
            cur.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    (SELECT MAX(id) IS NOT NULL FROM {table})
                )
                """
            )
