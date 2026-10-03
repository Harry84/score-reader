"""Match-history reads for the campaign project's Commander Q&A (its
HERA-MCP-BUILD-PLAN.md build step 1): seasons, a head-to-head between two
teams, and one match's full scoreboard. Read-only, same "narrative bot only
reads" contract as api/reads.py.

Teams are addressed by name in get_matchup(): `teams` (what matches
reference) and `ref_teams` (what /teams lists) share names but not ids, so a
name is the one key a caller can't get wrong.
"""


def list_seasons(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id, s.name, COUNT(m.id)
            FROM seasons s LEFT JOIN matches m ON m.season_id = s.id
            GROUP BY s.id, s.name ORDER BY s.id
            """
        )
        rows = cur.fetchall()
    return [{"season_id": r[0], "name": r[1], "match_count": r[2]} for r in rows]


def _team_names(pg_conn, team_ids):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, name FROM teams WHERE id = ANY(%s)", (list(team_ids),))
        return dict(cur.fetchall())


def _team_id(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id FROM teams WHERE LOWER(name) = LOWER(%s) ORDER BY id LIMIT 1", (name,))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"No team named {name!r}")
    return row[0]


def get_matchup(pg_conn, team_a, team_b, season_id=None, campaign_id=None):
    """Every match between the teams named `team_a` and `team_b` (either
    side, names case-insensitive), newest first, plus each team's wins.
    Raises ValueError for an unknown team name; an empty `matches` list
    means they've never met (under the given filters)."""
    team_a, team_b = _team_id(pg_conn, team_a), _team_id(pg_conn, team_b)
    names = _team_names(pg_conn, (team_a, team_b))

    sql = """
        SELECT m.id, m.match_date, m.season_id, s.name, m.campaign_id, m.match_type,
               m.imperial_team_id, m.rebel_team_id, m.winner
        FROM matches m LEFT JOIN seasons s ON s.id = m.season_id
        WHERE ((m.imperial_team_id = %s AND m.rebel_team_id = %s)
            OR (m.imperial_team_id = %s AND m.rebel_team_id = %s))
    """
    params = [team_a, team_b, team_b, team_a]
    if season_id is not None:
        sql += " AND m.season_id = %s"
        params.append(season_id)
    if campaign_id is not None:
        sql += " AND m.campaign_id = %s"
        params.append(campaign_id)
    sql += " ORDER BY m.match_date DESC NULLS LAST, m.id DESC"
    with pg_conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    wins = {team_a: 0, team_b: 0}
    matches = []
    for (match_id, match_date, season, season_name, campaign, match_type,
         imperial_id, rebel_id, winner) in rows:
        winner_id = imperial_id if winner == "IMPERIAL" else rebel_id if winner == "REBEL" else None
        if winner_id in wins:
            wins[winner_id] += 1
        matches.append({
            "match_id": match_id,
            "match_date": match_date.isoformat() if match_date else None,
            "season_id": season,
            "season": season_name,
            "campaign_id": campaign,
            "match_type": match_type,
            "imperial_team": names[imperial_id],
            "rebel_team": names[rebel_id],
            "winner": winner,
            "winner_team": names.get(winner_id),
        })
    return {
        "team_a": {"name": names[team_a], "wins": wins[team_a]},
        "team_b": {"name": names[team_b], "wins": wins[team_b]},
        "matches": matches,
    }


def get_match_detail(pg_conn, match_id):
    """One match with its full per-player scoreboard, or None if there's no
    such match."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.match_date, m.season_id, s.name, m.campaign_id, m.turn_id, m.system_id,
                   m.match_type, m.imperial_team_id, m.rebel_team_id, m.winner
            FROM matches m LEFT JOIN seasons s ON s.id = m.season_id
            WHERE m.id = %s
            """,
            (match_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        (match_date, season_id, season_name, campaign_id, turn_id, system_id,
         match_type, imperial_id, rebel_id, winner) = row
        cur.execute(
            """
            SELECT faction, player_name, role, score, kills, deaths, assists,
                   ai_kills, cap_ship_damage, is_subbing
            FROM player_stats WHERE match_id = %s ORDER BY faction, score DESC NULLS LAST, id
            """,
            (match_id,),
        )
        stats = cur.fetchall()

    names = _team_names(pg_conn, {t for t in (imperial_id, rebel_id) if t is not None})
    players = {"imperial": [], "rebel": []}
    for (faction, player, role, score, kills, deaths, assists,
         ai_kills, cap_ship_damage, is_subbing) in stats:
        players[faction.lower()].append({
            "player": player, "role": role, "score": score, "kills": kills,
            "deaths": deaths, "assists": assists, "ai_kills": ai_kills,
            "cap_ship_damage": cap_ship_damage, "is_subbing": is_subbing,
        })
    return {
        "match_id": match_id,
        "match_date": match_date.isoformat() if match_date else None,
        "season_id": season_id,
        "season": season_name,
        "campaign_id": campaign_id,
        "turn_id": turn_id,
        "system_id": system_id,
        "match_type": match_type,
        "imperial_team": names.get(imperial_id),
        "rebel_team": names.get(rebel_id),
        "winner": winner,
        "players": players,
    }
