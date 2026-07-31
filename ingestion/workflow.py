"""Ingestion workflow core (ADR-0005): turns an extracted screenshot into a
persisted Match, pausing on pending_matches for anything ambiguous.

Ambiguity types handled, each pausing at a distinct status and resuming via
submit_answer: unrecognized player name (awaiting_player_match:<name>), no
clear-majority team assignment for match_type "team"
(awaiting_team_assignment:<faction>), and no primary role on record
(awaiting_role:<name>). match_type "pickup"/"ranked" never pause for team
assignment at all - they use a fixed generic placeholder team instead
(GENERIC_TEAM_NAMES) and leave player_stats.team_id NULL, matching the
existing system's behavior.
"""

import difflib
import hashlib
import json
from collections import Counter

from stats.player_elo import recompute_player_elo
from stats.team_elo import recompute_team_elo


def _player_hash(name):
    return hashlib.sha256(name.encode()).hexdigest()[:16]


def _find_ref_player(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, primary_team_id, primary_role FROM ref_players WHERE name = %s",
            (name,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "primary_team_id": row[1], "primary_role": row[2]}


def _get_ref_player_by_id(pg_conn, ref_player_id):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, primary_team_id, primary_role FROM ref_players WHERE id = %s",
            (ref_player_id,),
        )
        row = cur.fetchone()
    return {"id": row[0], "primary_team_id": row[1], "primary_role": row[2]}


def _find_player_candidates(pg_conn, name, limit=3, cutoff=0.6):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id, name FROM ref_players")
        all_players = cur.fetchall()

    id_by_name = {player_name: player_id for player_id, player_name in all_players}
    close_names = difflib.get_close_matches(
        name, id_by_name.keys(), n=limit, cutoff=cutoff
    )
    return [{"id": id_by_name[n], "name": n} for n in close_names]


def _get_or_create_team(pg_conn, ref_team_id):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id FROM teams WHERE reference_id = %s", (ref_team_id,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("SELECT name FROM ref_teams WHERE id = %s", (ref_team_id,))
        (name,) = cur.fetchone()
        cur.execute(
            "INSERT INTO teams (name, reference_id) VALUES (%s, %s) RETURNING id",
            (name, ref_team_id),
        )
        return cur.fetchone()[0]


# Generic placeholder team names for match types with no real team
# assignment, matching the existing system's naming exactly (README.md /
# ELO_LADDER_README.md) since other tooling may reference these by name.
GENERIC_TEAM_NAMES = {
    "pickup": {"imperial": "Imp_pickup_team", "rebel": "NR_pickup_team"},
    "ranked": {"imperial": "Imperial_ranked_team", "rebel": "NR_ranked_team"},
}


def _get_or_create_team_by_name(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id FROM teams WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("INSERT INTO teams (name) VALUES (%s) RETURNING id", (name,))
        return cur.fetchone()[0]


def _get_or_create_player(pg_conn, ref_player_id):
    """Returns (player_id, canonical_name). The players row always uses the
    reference DB's canonical name, never the as-typed name from a screenshot
    (which may be a typo an earlier ambiguity step resolved past)."""
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, name FROM players WHERE reference_id = %s", (ref_player_id,)
        )
        row = cur.fetchone()
        if row:
            return row[0], row[1]
        cur.execute("SELECT name FROM ref_players WHERE id = %s", (ref_player_id,))
        (canonical_name,) = cur.fetchone()
        cur.execute(
            "INSERT INTO players (name, reference_id, player_hash) VALUES (%s, %s, %s) RETURNING id",
            (canonical_name, ref_player_id, _player_hash(canonical_name)),
        )
        return cur.fetchone()[0], canonical_name


def _majority_team_id(resolved_players):
    """The most common primary_team_id among a faction's resolved players, or
    None if there's no clear majority (a tie, or nobody has a primary team)."""
    counts = Counter(
        rp["ref_player"]["primary_team_id"]
        for rp in resolved_players
        if rp["ref_player"]["primary_team_id"] is not None
    )
    if not counts:
        return None
    ranked = counts.most_common()
    top_id, top_count = ranked[0]
    if len(ranked) > 1 and ranked[1][1] == top_count:
        return None
    return top_id


def _team_candidates(pg_conn, resolved_players):
    ref_team_ids = {
        rp["ref_player"]["primary_team_id"]
        for rp in resolved_players
        if rp["ref_player"]["primary_team_id"] is not None
    }
    if not ref_team_ids:
        return []
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, name FROM ref_teams WHERE id = ANY(%s)", (list(ref_team_ids),)
        )
        rows = cur.fetchall()
    return [{"id": i, "name": n} for i, n in rows]


ROLES = ["Farmer", "Flex", "Support"]


def _resolve_faction(
    pg_conn,
    faction,
    faction_players,
    match_type,
    player_resolutions,
    team_assignments,
    role_overrides,
):
    """Returns (resolved, pause). Exactly one of the two is not None: resolved
    when every player, their role, and the faction's team assignment are
    unambiguous, or pause describing the first ambiguity hit, to be applied
    to the pending_matches row by the caller."""
    resolved_players = []
    for p in faction_players:
        override = player_resolutions.get(p["player"])
        if override is not None:
            ref_player = _get_ref_player_by_id(pg_conn, override["ref_player_id"])
        else:
            ref_player = _find_ref_player(pg_conn, p["player"])

        if ref_player is None:
            candidates = _find_player_candidates(pg_conn, p["player"])
            pause = {
                "status": f"awaiting_player_match:{p['player']}",
                "question": {
                    "type": "player_match",
                    "player_name": p["player"],
                    "candidates": candidates,
                },
            }
            return None, pause

        role = role_overrides.get(p["player"], ref_player["primary_role"])
        if role is None:
            pause = {
                "status": f"awaiting_role:{p['player']}",
                "question": {
                    "type": "role",
                    "player_name": p["player"],
                    "candidates": ROLES,
                },
            }
            return None, pause

        resolved_players.append({**p, "ref_player": ref_player, "role": role})

    if match_type != "team":
        # Pickup/ranked matches never associate players with a team - no
        # majority vote, no pause, ever (existing behavior: player_stats.team_id
        # stays NULL, and the match itself uses a generic placeholder team;
        # see GENERIC_TEAM_NAMES / _persist).
        return {"players": resolved_players, "ref_team_id": None}, None

    if faction in team_assignments:
        ref_team_id = team_assignments[faction]
    else:
        ref_team_id = _majority_team_id(resolved_players)
        if ref_team_id is None:
            pause = {
                "status": f"awaiting_team_assignment:{faction}",
                "question": {
                    "type": "team_assignment",
                    "faction": faction,
                    "candidates": _team_candidates(pg_conn, resolved_players),
                },
            }
            return None, pause

    return {"players": resolved_players, "ref_team_id": ref_team_id}, None


def _load_pending_match(pg_conn, pending_match_id):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT campaign_id, turn_id, system_id, match_type, extracted_data, answers
            FROM pending_matches WHERE id = %s
            """,
            (pending_match_id,),
        )
        campaign_id, turn_id, system_id, match_type, extracted_data, answers = cur.fetchone()
    return {
        "campaign_id": campaign_id,
        "turn_id": turn_id,
        "system_id": system_id,
        "match_type": match_type,
        "extracted_data": extracted_data,
        "answers": answers,
    }


def _pause(pg_conn, pending_match_id, pause):
    with pg_conn.cursor() as cur:
        cur.execute(
            "UPDATE pending_matches SET status = %s, updated_at = now() WHERE id = %s",
            (pause["status"], pending_match_id),
        )
    pg_conn.commit()
    return {
        "status": pause["status"],
        "pending_match_id": pending_match_id,
        "question": pause["question"],
    }


def _normalize_winner(match_result):
    """Matches stats_reader.modules.match_processor's normalization: the raw
    extracted match_result text ("IMPERIAL VICTORY") becomes the plain
    faction name stored in matches.winner and relied on by ELO/report
    queries elsewhere in the codebase."""
    upper = match_result.upper()
    if "IMPERIAL" in upper or "EMPIRE" in upper:
        return "IMPERIAL"
    if "REBEL" in upper or "NEW REPUBLIC" in upper or "REPUBLIC" in upper:
        return "REBEL"
    return "UNKNOWN"


def _persist(pg_conn, pending_match_id, pending_match, resolved):
    extracted_data = pending_match["extracted_data"]
    winner = _normalize_winner(extracted_data["match_result"])
    match_type = pending_match["match_type"]

    if match_type == "team":
        team_id_by_faction = {
            faction: _get_or_create_team(pg_conn, resolved[faction]["ref_team_id"])
            for faction in ("imperial", "rebel")
        }
    else:
        generic_names = GENERIC_TEAM_NAMES[match_type]
        team_id_by_faction = {
            faction: _get_or_create_team_by_name(pg_conn, generic_names[faction])
            for faction in ("imperial", "rebel")
        }

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO matches (imperial_team_id, rebel_team_id, winner, match_type, campaign_id, turn_id, system_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                team_id_by_faction["imperial"],
                team_id_by_faction["rebel"],
                winner,
                match_type,
                pending_match["campaign_id"],
                pending_match["turn_id"],
                pending_match["system_id"],
            ),
        )
        match_id = cur.fetchone()[0]

        if winner == "IMPERIAL":
            cur.execute(
                "UPDATE teams SET wins = wins + 1 WHERE id = %s",
                (team_id_by_faction["imperial"],),
            )
            cur.execute(
                "UPDATE teams SET losses = losses + 1 WHERE id = %s",
                (team_id_by_faction["rebel"],),
            )
        elif winner == "REBEL":
            cur.execute(
                "UPDATE teams SET wins = wins + 1 WHERE id = %s",
                (team_id_by_faction["rebel"],),
            )
            cur.execute(
                "UPDATE teams SET losses = losses + 1 WHERE id = %s",
                (team_id_by_faction["imperial"],),
            )

        for faction, data in resolved.items():
            # player_stats.team_id stays NULL for pickup/ranked - those
            # matches associate a player with no specific team at all, unlike
            # the generic placeholder team recorded at the match level above.
            player_team_id = team_id_by_faction[faction] if match_type == "team" else None
            for rp in data["players"]:
                player_id, canonical_name = _get_or_create_player(
                    pg_conn, rp["ref_player"]["id"]
                )
                is_subbing = (
                    match_type == "team"
                    and rp["ref_player"]["primary_team_id"] != data["ref_team_id"]
                )
                cur.execute(
                    """
                    INSERT INTO player_stats
                        (match_id, player_id, player_name, player_hash, team_id, faction,
                         position, role, score, kills, deaths, assists, ai_kills,
                         cap_ship_damage, is_subbing)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        match_id,
                        player_id,
                        rp["player"],
                        _player_hash(canonical_name),
                        player_team_id,
                        faction.upper(),
                        rp["position"],
                        rp["role"],
                        rp["score"],
                        rp["kills"],
                        rp["deaths"],
                        rp["assists"],
                        rp["ai_kills"],
                        rp["cap_ship_damage"],
                        is_subbing,
                    ),
                )

        cur.execute(
            "UPDATE pending_matches SET status = 'persisted', updated_at = now() WHERE id = %s",
            (pending_match_id,),
        )
    pg_conn.commit()

    if match_type == "team":
        recompute_team_elo(pg_conn, pending_match["campaign_id"])
    else:
        recompute_player_elo(pg_conn, pending_match["campaign_id"], match_type)

    summary = _build_match_summary(pg_conn, match_id)
    summary["pending_match_id"] = pending_match_id
    return summary


def _build_match_summary(pg_conn, match_id):
    """The persisted-match shape returned by _persist and by the edit_*
    functions below - always read back from the DB rather than assembled
    from in-memory state, so an edited match's summary reflects what's
    actually stored."""
    with pg_conn.cursor() as cur:
        cur.execute("SELECT winner FROM matches WHERE id = %s", (match_id,))
        (winner,) = cur.fetchone()
        cur.execute(
            """
            SELECT faction, player_name, role, score, kills, deaths, assists, ai_kills, cap_ship_damage
            FROM player_stats WHERE match_id = %s ORDER BY faction, id
            """,
            (match_id,),
        )
        rows = cur.fetchall()

    players = {"imperial": [], "rebel": []}
    for faction, player, role, score, kills, deaths, assists, ai_kills, cap_ship_damage in rows:
        players[faction.lower()].append(
            {
                "player": player,
                "role": role,
                "score": score,
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "ai_kills": ai_kills,
                "cap_ship_damage": cap_ship_damage,
            }
        )

    return {"status": "persisted", "match_id": match_id, "winner": winner, "players": players}


def _recompute_for_match(pg_conn, match_id):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT campaign_id, match_type FROM matches WHERE id = %s", (match_id,))
        campaign_id, match_type = cur.fetchone()
    if match_type == "team":
        recompute_team_elo(pg_conn, campaign_id)
    else:
        recompute_player_elo(pg_conn, campaign_id, match_type)


EDITABLE_PLAYER_FIELDS = {"role", "score", "kills", "deaths", "assists", "ai_kills", "cap_ship_damage"}


def edit_match_player(pg_conn, match_id, player_name, updates):
    """Correct a persisted match's per-player stats or reassign a misread
    name to the correct canonical player - the same fields
    stats_reader/data_cleaner.py's old pre-DB CLI review step let you fix,
    now applied to an already-persisted Postgres match instead of a JSON
    file. Safe to call any time after persist: recompute_player_elo/
    recompute_team_elo always replay the full (campaign_id, match_type)
    history from scratch, so there's no incremental state to undo.
    """
    updates = dict(updates)
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM player_stats WHERE match_id = %s AND player_name = %s",
            (match_id, player_name),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"No player '{player_name}' on match {match_id}")
        player_stats_id = row[0]

        new_name = updates.pop("name", None)
        if new_name is not None:
            ref_player = _find_ref_player(pg_conn, new_name)
            if ref_player is None:
                raise ValueError(f"No canonical player named '{new_name}'")
            player_id, canonical_name = _get_or_create_player(pg_conn, ref_player["id"])
            cur.execute(
                "UPDATE player_stats SET player_id = %s, player_name = %s, player_hash = %s WHERE id = %s",
                (player_id, new_name, _player_hash(canonical_name), player_stats_id),
            )

        unknown = set(updates) - EDITABLE_PLAYER_FIELDS
        if unknown:
            raise ValueError(f"Can't edit field(s): {', '.join(sorted(unknown))}")

        if updates:
            assignments = ", ".join(f"{field} = %s" for field in updates)
            cur.execute(
                f"UPDATE player_stats SET {assignments} WHERE id = %s",
                (*updates.values(), player_stats_id),
            )
    pg_conn.commit()

    _recompute_for_match(pg_conn, match_id)
    return _build_match_summary(pg_conn, match_id)


def edit_match_winner(pg_conn, match_id, winner):
    """Correct a persisted match's winner, fixing up teams.wins/losses to
    match, then re-running ELO the same way edit_match_player does."""
    winner = winner.upper()
    if winner not in ("IMPERIAL", "REBEL"):
        raise ValueError("winner must be 'IMPERIAL' or 'REBEL'")

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT winner, imperial_team_id, rebel_team_id FROM matches WHERE id = %s", (match_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"No match with id {match_id}")
        old_winner, imperial_team_id, rebel_team_id = row

        if winner != old_winner:
            if old_winner in ("IMPERIAL", "REBEL"):
                old_winner_team = imperial_team_id if old_winner == "IMPERIAL" else rebel_team_id
                old_loser_team = rebel_team_id if old_winner == "IMPERIAL" else imperial_team_id
                cur.execute("UPDATE teams SET wins = wins - 1 WHERE id = %s", (old_winner_team,))
                cur.execute("UPDATE teams SET losses = losses - 1 WHERE id = %s", (old_loser_team,))

            new_winner_team = imperial_team_id if winner == "IMPERIAL" else rebel_team_id
            new_loser_team = rebel_team_id if winner == "IMPERIAL" else imperial_team_id
            cur.execute("UPDATE teams SET wins = wins + 1 WHERE id = %s", (new_winner_team,))
            cur.execute("UPDATE teams SET losses = losses + 1 WHERE id = %s", (new_loser_team,))
            cur.execute("UPDATE matches SET winner = %s WHERE id = %s", (winner, match_id))
    pg_conn.commit()

    _recompute_for_match(pg_conn, match_id)
    return _build_match_summary(pg_conn, match_id)


def _advance(pg_conn, pending_match_id):
    pending_match = _load_pending_match(pg_conn, pending_match_id)
    answers = pending_match["answers"]
    player_resolutions = answers.get("player_resolutions", {})
    team_assignments = answers.get("team_assignments", {})
    role_overrides = answers.get("role_overrides", {})

    resolved = {}
    for faction in ("imperial", "rebel"):
        faction_resolved, pause = _resolve_faction(
            pg_conn,
            faction,
            pending_match["extracted_data"]["teams"][faction]["players"],
            pending_match["match_type"],
            player_resolutions,
            team_assignments,
            role_overrides,
        )
        if pause is not None:
            return _pause(pg_conn, pending_match_id, pause)
        resolved[faction] = faction_resolved

    return _persist(pg_conn, pending_match_id, pending_match, resolved)


def start_ingestion(
    pg_conn, campaign_id, turn_id, system_id, match_type, screenshot_ref, extracted_data
):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pending_matches
                (campaign_id, turn_id, system_id, match_type, screenshot_ref, status, extracted_data, answers)
            VALUES (%s, %s, %s, %s, %s, 'extracted', %s, '{}'::jsonb)
            RETURNING id
            """,
            (campaign_id, turn_id, system_id, match_type, screenshot_ref, json.dumps(extracted_data)),
        )
        pending_match_id = cur.fetchone()[0]
    pg_conn.commit()

    return _advance(pg_conn, pending_match_id)


def submit_answer(pg_conn, pending_match_id, answer):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT status, answers FROM pending_matches WHERE id = %s",
            (pending_match_id,),
        )
        status, answers = cur.fetchone()

    if status.startswith("awaiting_player_match:"):
        player_name = status[len("awaiting_player_match:") :]
        player_resolutions = answers.setdefault("player_resolutions", {})
        player_resolutions[player_name] = answer
    elif status.startswith("awaiting_team_assignment:"):
        faction = status[len("awaiting_team_assignment:") :]
        team_assignments = answers.setdefault("team_assignments", {})
        team_assignments[faction] = answer["ref_team_id"]
    elif status.startswith("awaiting_role:"):
        player_name = status[len("awaiting_role:") :]
        role_overrides = answers.setdefault("role_overrides", {})
        role_overrides[player_name] = answer["role"]
    else:
        raise NotImplementedError(f"Cannot answer status '{status}' yet")

    with pg_conn.cursor() as cur:
        cur.execute(
            "UPDATE pending_matches SET answers = %s, updated_at = now() WHERE id = %s",
            (json.dumps(answers), pending_match_id),
        )
    pg_conn.commit()

    return _advance(pg_conn, pending_match_id)
