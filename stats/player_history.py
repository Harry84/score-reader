"""Per-player reads for the campaign project's Commander Q&A: a player's
rating history, their career stats, and stat leaderboards. Read-only, same
"narrative bot only reads" contract as api/reads.py.

Players are addressed by name (case-insensitive), as in stats/history.py.
Ratios (K/D) are computed here so a caller never has to do arithmetic on
the numbers it quotes.
"""

from stats.player_elo import GENERAL

STATS = ["score", "kills", "deaths", "assists", "ai_kills", "cap_ship_damage"]
LEADER_STATS = STATS + ["kd"]
PER = ["total", "average"]


def _player(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, name FROM players WHERE LOWER(name) = LOWER(%s) ORDER BY id LIMIT 1", (name,))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"No player named {name!r}")
    return row


def _kd(kills, deaths):
    return round(kills / max(deaths, 1), 2)


def get_player_elo_history(pg_conn, campaign_id, player, match_type, role=GENERAL):
    """One player's rating after each rated match, newest first."""
    player_id, name = _player(pg_conn, player)
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT h.match_id, m.match_date, h.faction, h.old_rating, h.new_rating, h.winner
            FROM player_elo_history h JOIN matches m ON m.id = h.match_id
            WHERE h.campaign_id = %s AND h.match_type = %s AND h.role = %s AND h.player_id = %s
            ORDER BY m.match_date DESC, h.match_id DESC
            """,
            (campaign_id, match_type, role, player_id),
        )
        rows = cur.fetchall()
    return {
        "player": name, "campaign_id": campaign_id, "match_type": match_type, "role": role,
        "history": [
            {"match_id": r[0], "match_date": r[1].isoformat() if r[1] else None, "faction": r[2],
             "old_rating": round(float(r[3]), 1), "new_rating": round(float(r[4]), 1),
             "change": round(float(r[4]) - float(r[3]), 1), "won": r[2] == r[5]}
            for r in rows
        ],
    }


def _filters(campaign_id, match_type, role=None):
    where, params = [], []
    if campaign_id:
        where.append("m.campaign_id = %s")
        params.append(campaign_id)
    if match_type:
        where.append("m.match_type = %s")
        params.append(match_type)
    if role:
        where.append("LOWER(ps.role) = LOWER(%s)")
        params.append(role)
    return where, params


def get_player_career(pg_conn, player, campaign_id=None, match_type=None, recent=5):
    """One player's stats across every match they're recorded in: totals,
    averages, K/D, wins, a breakdown by role, and their latest matches."""
    player_id, name = _player(pg_conn, player)
    where, params = _filters(campaign_id, match_type)
    clause = "".join(f" AND {w}" for w in where)
    with pg_conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT ps.match_id, m.match_date, m.match_type, ps.role, ps.faction, m.winner,
                   {", ".join(f"COALESCE(ps.{s}, 0)" for s in STATS)}
            FROM player_stats ps JOIN matches m ON m.id = ps.match_id
            WHERE ps.player_id = %s{clause}
            ORDER BY m.match_date DESC, ps.match_id DESC
            """,
            [player_id] + params,
        )
        rows = cur.fetchall()
    n = len(rows)
    totals = {s: sum(r[6 + i] for r in rows) for i, s in enumerate(STATS)}
    wins = sum(1 for r in rows if r[4] == r[5])
    by_role = {}
    for r in rows:
        role = r[3] or "unknown"
        entry = by_role.setdefault(role, {"matches": 0, "score": 0})
        entry["matches"] += 1
        entry["score"] += r[6]
    return {
        "player": name, "matches": n, "wins": wins, "losses": n - wins,
        "totals": totals,
        "averages": {s: round(totals[s] / n, 1) for s in STATS} if n else {},
        "kd": _kd(totals["kills"], totals["deaths"]) if n else None,
        "by_role": {role: {"matches": e["matches"], "average_score": round(e["score"] / e["matches"], 1)}
                    for role, e in by_role.items()},
        "recent": [
            {"match_id": r[0], "match_date": r[1].isoformat() if r[1] else None, "match_type": r[2],
             "role": r[3], "faction": r[4], "won": r[4] == r[5],
             **{s: r[6 + i] for i, s in enumerate(STATS)}}
            for r in rows[:recent]
        ],
    }


def get_stat_leaders(pg_conn, stat, per="total", campaign_id=None, match_type=None, role=None,
                     min_matches=1, limit=10):
    """Players ranked by one stat, as a total or a per-match average (K/D is
    always a ratio of totals). Raises ValueError for an unknown stat or per."""
    if stat not in LEADER_STATS:
        raise ValueError(f"stat must be one of {LEADER_STATS}")
    if per not in PER:
        raise ValueError(f"per must be one of {PER}")
    if stat == "kd":
        value = "SUM(COALESCE(ps.kills, 0))::float / GREATEST(SUM(COALESCE(ps.deaths, 0)), 1)"
    else:
        value = f"{'SUM' if per == 'total' else 'AVG'}(COALESCE(ps.{stat}, 0))"
    where, params = _filters(campaign_id, match_type, role)
    clause = "".join(f" AND {w}" for w in where)
    with pg_conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT p.name, COUNT(*) AS matches, {value} AS value
            FROM player_stats ps JOIN matches m ON m.id = ps.match_id JOIN players p ON p.id = ps.player_id
            WHERE TRUE{clause}
            GROUP BY p.id, p.name HAVING COUNT(*) >= %s
            ORDER BY value DESC, p.name LIMIT %s
            """,
            params + [min_matches, limit],
        )
        rows = cur.fetchall()
    return {
        "stat": stat, "per": "ratio" if stat == "kd" else per,
        "filters": {"campaign_id": campaign_id, "match_type": match_type, "role": role, "min_matches": min_matches},
        "leaders": [{"rank": i + 1, "player": r[0], "matches": r[1], "value": round(float(r[2]), 2)}
                    for i, r in enumerate(rows)],
    }
