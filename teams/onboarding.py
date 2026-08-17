"""Team onboarding (ROADMAP Phase 2, ADR-0008): create teams/players and
manage roster membership via the reference DB.

Two trust levels, enforced differently: create_team/create_player/set_captain
are Admin-only actions, trusted implicitly from whatever calls this module
(the score bot only exposes them to Discord admins - ADR-0008).
attach_player_to_roster is Captain-only and independently verifies the
caller against ref_teams.captain_discord_id rather than trusting the caller.
"""


def create_team(pg_conn, name, alias=None, faction=None):
    """Find-or-create a ref_teams row by name (idempotent, admin action).

    faction is only applied on genuine creation -- re-running against an
    existing team name never overwrites its faction (same
    find-or-create-is-idempotent contract as the rest of this function).
    """
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, name, captain_discord_id, faction FROM ref_teams WHERE name = %s", (name,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO ref_teams (name, alias, faction) VALUES (%s, %s, %s) "
                "RETURNING id, name, captain_discord_id, faction",
                (name, alias, faction),
            )
            row = cur.fetchone()
    pg_conn.commit()
    return {"id": row[0], "name": row[1], "captain_discord_id": row[2], "faction": row[3]}


def create_player(pg_conn, name, primary_team_id=None, primary_role=None, alias=None, source_file=None):
    """Create a genuinely new canonical ref_players row (admin action)."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ref_players (name, primary_team_id, primary_role, alias, source_file)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, primary_team_id, primary_role
            """,
            (name, primary_team_id, primary_role, alias, source_file),
        )
        row = cur.fetchone()
    pg_conn.commit()
    return {"id": row[0], "name": row[1], "primary_team_id": row[2], "primary_role": row[3]}


def set_captain(pg_conn, team_id, captain_discord_id):
    """Assign/change a team's captain (admin action)."""
    with pg_conn.cursor() as cur:
        cur.execute(
            "UPDATE ref_teams SET captain_discord_id = %s WHERE id = %s RETURNING id, name, captain_discord_id",
            (captain_discord_id, team_id),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"No team with id {team_id}")
    pg_conn.commit()
    return {"id": row[0], "name": row[1], "captain_discord_id": row[2]}


def list_teams(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, name, captain_discord_id, faction FROM ref_teams ORDER BY name")
        rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "captain_discord_id": r[2], "faction": r[3]} for r in rows]


def get_team(pg_conn, team_id):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, captain_discord_id, faction FROM ref_teams WHERE id = %s", (team_id,)
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"No team with id {team_id}")
    return {"id": row[0], "name": row[1], "captain_discord_id": row[2], "faction": row[3]}


def get_team_roster(pg_conn, team_id):
    """List a team's roster (ROADMAP Phase 5 - campaign project read).

    Raises ValueError if the team doesn't exist, mirroring get_team.
    """
    get_team(pg_conn, team_id)
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, name FROM ref_players WHERE primary_team_id = %s ORDER BY name",
            (team_id,),
        )
        rows = cur.fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


def find_players_by_name(pg_conn, name):
    """Case-insensitive partial-name search over ref_players (open lookup).

    Used by the score bot to resolve a typed player name into a
    ref_player_id before calling attach_player_to_roster - may return
    several candidates if the name is ambiguous.
    """
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, primary_team_id, primary_role, alias
            FROM ref_players
            WHERE name ILIKE %s
            ORDER BY name
            """,
            (f"%{name}%",),
        )
        rows = cur.fetchall()
    return [
        {"id": r[0], "name": r[1], "primary_team_id": r[2], "primary_role": r[3], "alias": r[4]}
        for r in rows
    ]


def attach_player_to_roster(pg_conn, team_id, requesting_discord_id, ref_player_id):
    """Attach an existing canonical player to a team's roster (captain action).

    Raises ValueError if the team doesn't exist, PermissionError if the
    requester isn't that team's captain.
    """
    team = get_team(pg_conn, team_id)

    if team["captain_discord_id"] != requesting_discord_id:
        raise PermissionError(
            f"'{requesting_discord_id}' is not the captain of team '{team['name']}'"
        )

    with pg_conn.cursor() as cur:
        cur.execute(
            "UPDATE ref_players SET primary_team_id = %s WHERE id = %s",
            (team_id, ref_player_id),
        )
    pg_conn.commit()
