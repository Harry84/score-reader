"""Ingestion workflow core (ADR-0005): turns an extracted screenshot into a
persisted Match, pausing on pending_matches for anything ambiguous.

Ambiguity types handled, each pausing at a distinct status and resuming via
submit_answer: unrecognized player name (awaiting_player_match:<name>), and
no clear-majority team assignment for match_type "team"
(awaiting_team_assignment:<faction>). match_type "pickup"/"ranked" never
pause for team assignment at all - they use a fixed generic placeholder
team instead (GENERIC_TEAM_NAMES) and leave player_stats.team_id NULL,
matching the existing system's behavior.

Two more pause types validate the raw extraction itself, before any player
identity/team resolution runs: a faction with other than EXPECTED_ROSTER_SIZE
players (awaiting_roster_size:<faction> - confirm to proceed anyway, e.g. a
genuine no-show) and a player record missing a required field entirely
(awaiting_missing_field:<player>:<field> - supply the correct value). Both
guard against a bad/partial vision extraction silently becoming wrong stats,
same motivation as the identity/team pauses above.

A missing primary role used to pause too (awaiting_role) but no longer
does: role only affects which role-ELO ladder a player lands on, not who
played or who won, so it's not worth blocking persist over. It's left
NULL (a legitimate "no role this match" state, e.g. genuine multi-roling)
and can be set/cleared afterward via edit_match_player.
"""

import difflib
import hashlib
import json
from collections import Counter

from stats.player_elo import recompute_player_elo
from stats.team_elo import recompute_team_elo


class DuplicateMatchError(Exception):
    """Raised when a match with this exact fingerprint already exists in
    this campaign - either the same screenshot re-uploaded byte-for-byte
    (check_duplicate_image, reason="image") or the same stats extracted
    from a different screenshot (_check_duplicate, reason="stats"). Hard
    stop, no override - if this is ever a false positive, fix/delete the
    existing match directly rather than forcing a second one through.
    """

    _REASON_DESCRIPTIONS = {
        "image": "this exact screenshot was already uploaded",
        "stats": "the same stats were already recorded from a different screenshot",
    }

    def __init__(self, existing_match_id, existing_summary, reason):
        self.existing_match_id = existing_match_id
        self.existing_summary = existing_summary
        self.reason = reason
        description = self._REASON_DESCRIPTIONS[reason]
        super().__init__(f"Match already entered as match {existing_match_id} ({description})")


def _player_hash(name):
    return hashlib.sha256(name.encode()).hexdigest()[:16]


def _compute_stats_hash(extracted_data):
    """Canonical fingerprint of a match's actual stats, independent of
    extraction order - used to catch the same screenshot being ingested
    twice. Deliberately excludes screenshot_ref/turn_id/system_id: those
    identify *where* a match was posted, not what happened in it, and a
    real duplicate could plausibly get reposted with a different
    screenshot_ref.
    """
    canonical = {
        "match_result": extracted_data["match_result"],
        "teams": {
            faction: sorted(
                (
                    p.get("player"),
                    p.get("position"),
                    p.get("score"),
                    p.get("kills"),
                    p.get("deaths"),
                    p.get("assists"),
                    p.get("ai_kills"),
                    p.get("cap_ship_damage"),
                )
                for p in extracted_data["teams"][faction]["players"]
            )
            for faction in ("imperial", "rebel")
        },
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:16]


def _check_duplicate(pg_conn, campaign_id, extracted_data):
    stats_hash = _compute_stats_hash(extracted_data)
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM matches WHERE campaign_id = %s AND stats_hash = %s",
            (campaign_id, stats_hash),
        )
        row = cur.fetchone()
    if row is not None:
        raise DuplicateMatchError(row[0], _build_match_summary(pg_conn, row[0]), reason="stats")


def check_duplicate_image(pg_conn, campaign_id, image_bytes):
    """Cheap pre-extraction duplicate guard: rejects a byte-for-byte repeat
    of an already-persisted screenshot before ever calling the (paid) Claude
    vision API. Narrower than _check_duplicate/_compute_stats_hash (which
    catches the same match re-extracted from a *different* image, e.g. a
    second genuine screenshot of the same result screen) - this only
    catches literally the same image file being posted twice. Same hard-stop
    DuplicateMatchError as the stats-based check, same rendering, same
    no-override rule. Not a private helper (unlike _check_duplicate) since
    it has to run in api/main.py before extraction, not inside
    start_ingestion which only ever sees already-extracted data.

    Returns the computed hash so the caller can pass it straight into
    start_ingestion without recomputing it.
    """
    image_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM matches WHERE campaign_id = %s AND image_hash = %s",
            (campaign_id, image_hash),
        )
        row = cur.fetchone()
    if row is not None:
        raise DuplicateMatchError(row[0], _build_match_summary(pg_conn, row[0]), reason="image")
    return image_hash


def _find_ref_player(pg_conn, name):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, primary_team_id, primary_role FROM ref_players WHERE name = %s",
            (name,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "primary_team_id": row[2], "primary_role": row[3]}


def _get_ref_player_by_id(pg_conn, ref_player_id):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, primary_team_id, primary_role FROM ref_players WHERE id = %s",
            (ref_player_id,),
        )
        row = cur.fetchone()
    return {"id": row[0], "name": row[1], "primary_team_id": row[2], "primary_role": row[3]}


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

# Squadrons is 5v5; assumed uniform across match_type since nothing in
# CONTEXT.md suggests otherwise. Revisit if a mode with a different squad
# size shows up.
EXPECTED_ROSTER_SIZE = 5
REQUIRED_NUMERIC_FIELDS = ["score", "kills", "deaths", "assists", "ai_kills", "cap_ship_damage"]
REQUIRED_STRING_FIELDS = ["position"]


def _validate_faction(faction, faction_players, answers):
    """Returns a pause dict if the raw extraction for this faction looks
    incomplete, else None. Checked before any player identity/team
    resolution - no point resolving identities against data that's already
    known to be short a player or missing a stat.

    Deliberately doesn't validate the "player" name field itself (a missing
    name is a different, rarer failure mode than a missing stat, and
    field_overrides below key by player name - there'd be nothing to key by).
    """
    if (
        len(faction_players) != EXPECTED_ROSTER_SIZE
        and faction not in answers.get("confirmed_roster_sizes", [])
    ):
        return {
            "status": f"awaiting_roster_size:{faction}",
            "question": {
                "type": "roster_size",
                "faction": faction,
                "count": len(faction_players),
                "expected": EXPECTED_ROSTER_SIZE,
            },
        }

    field_overrides = answers.get("field_overrides", {})
    for p in faction_players:
        overrides = field_overrides.get(p["player"], {})
        for field in REQUIRED_NUMERIC_FIELDS + REQUIRED_STRING_FIELDS:
            if field not in overrides and p.get(field) is None:
                return {
                    "status": f"awaiting_missing_field:{p['player']}:{field}",
                    "question": {
                        "type": "missing_field",
                        "player_name": p["player"],
                        "field": field,
                        "numeric": field in REQUIRED_NUMERIC_FIELDS,
                    },
                }

    return None


def _apply_field_overrides(faction_players, field_overrides):
    return [{**p, **field_overrides.get(p["player"], {})} for p in faction_players]


def _resolve_faction(
    pg_conn,
    faction,
    faction_players,
    match_type,
    player_resolutions,
    team_assignments,
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

        # No pause when a player has no primary_role on record: "no role" is
        # a legitimate persisted state (e.g. a genuine multi-role match),
        # fixable afterward via edit_match_player rather than blocking the
        # whole match on it.
        #
        # "player" is overwritten with the canonical ref_players name here -
        # not just p["player"] as-typed/extracted - so a player_match override
        # (an as-typed name that didn't match anyone) persists under their
        # correct name instead of the screenshot's typo.
        resolved_players.append(
            {**p, "player": ref_player["name"], "ref_player": ref_player, "role": ref_player["primary_role"]}
        )

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
            SELECT campaign_id, turn_id, system_id, match_type, extracted_data, answers, image_hash
            FROM pending_matches WHERE id = %s
            """,
            (pending_match_id,),
        )
        campaign_id, turn_id, system_id, match_type, extracted_data, answers, image_hash = cur.fetchone()
    return {
        "campaign_id": campaign_id,
        "turn_id": turn_id,
        "system_id": system_id,
        "match_type": match_type,
        "extracted_data": extracted_data,
        "answers": answers,
        "image_hash": image_hash,
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
    stats_hash = _compute_stats_hash(extracted_data)

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
            INSERT INTO matches (imperial_team_id, rebel_team_id, winner, match_type, campaign_id, turn_id, system_id, stats_hash, image_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                stats_hash,
                pending_match["image_hash"],
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

        if "role" in updates and updates["role"] is not None:
            matched = next((r for r in ROLES if r.lower() == str(updates["role"]).lower()), None)
            if matched is None:
                raise ValueError(f"'{updates['role']}' isn't a valid role. Use one of {', '.join(ROLES)}, or null to clear it.")
            updates["role"] = matched

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
    field_overrides = answers.get("field_overrides", {})

    resolved = {}
    for faction in ("imperial", "rebel"):
        faction_players = pending_match["extracted_data"]["teams"][faction]["players"]

        validation_pause = _validate_faction(faction, faction_players, answers)
        if validation_pause is not None:
            return _pause(pg_conn, pending_match_id, validation_pause)

        faction_players = _apply_field_overrides(faction_players, field_overrides)

        faction_resolved, pause = _resolve_faction(
            pg_conn,
            faction,
            faction_players,
            pending_match["match_type"],
            player_resolutions,
            team_assignments,
        )
        if pause is not None:
            return _pause(pg_conn, pending_match_id, pause)
        resolved[faction] = faction_resolved

    return _persist(pg_conn, pending_match_id, pending_match, resolved)


def start_ingestion(
    pg_conn, campaign_id, turn_id, system_id, match_type, screenshot_ref, extracted_data,
    image_hash=None,
):
    """image_hash: precomputed by check_duplicate_image (api/main.py calls it
    before extraction to avoid a wasted Claude call on an exact image repeat)
    - stored through to the eventual matches row so future posts can be
    checked against it too. Optional/defaults to None for callers (mostly
    tests) that don't go through that pre-check.
    """
    _check_duplicate(pg_conn, campaign_id, extracted_data)

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pending_matches
                (campaign_id, turn_id, system_id, match_type, screenshot_ref, status, extracted_data, answers, image_hash)
            VALUES (%s, %s, %s, %s, %s, 'extracted', %s, '{}'::jsonb, %s)
            RETURNING id
            """,
            (campaign_id, turn_id, system_id, match_type, screenshot_ref, json.dumps(extracted_data), image_hash),
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
    elif status.startswith("awaiting_roster_size:"):
        faction = status[len("awaiting_roster_size:") :]
        confirmed = answers.setdefault("confirmed_roster_sizes", [])
        if faction not in confirmed:
            confirmed.append(faction)
    elif status.startswith("awaiting_missing_field:"):
        player_name, field = status[len("awaiting_missing_field:") :].rsplit(":", 1)
        value = int(answer["value"]) if field in REQUIRED_NUMERIC_FIELDS else answer["value"]
        field_overrides = answers.setdefault("field_overrides", {})
        field_overrides.setdefault(player_name, {})[field] = value
    else:
        raise NotImplementedError(f"Cannot answer status '{status}' yet")

    with pg_conn.cursor() as cur:
        cur.execute(
            "UPDATE pending_matches SET answers = %s, updated_at = now() WHERE id = %s",
            (json.dumps(answers), pending_match_id),
        )
    pg_conn.commit()

    return _advance(pg_conn, pending_match_id)
