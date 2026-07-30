"""Ingestion workflow core (ADR-0005): turns an extracted screenshot into a
persisted Match, pausing on pending_matches for anything ambiguous.

This first slice only handles the fully-unambiguous case: every player
exactly matches an existing ref_players row, and each faction's players
agree on a single primary team. Ambiguity handling (unrecognized player,
disagreeing team assignment, subbing, role overrides) is added in later
slices.
"""

import hashlib
import json


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


def _get_or_create_player(pg_conn, name, ref_player_id):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id FROM players WHERE reference_id = %s", (ref_player_id,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO players (name, reference_id, player_hash) VALUES (%s, %s, %s) RETURNING id",
            (name, ref_player_id, _player_hash(name)),
        )
        return cur.fetchone()[0]


def _resolve_faction(pg_conn, faction_players):
    resolved_players = []
    for p in faction_players:
        ref_player = _find_ref_player(pg_conn, p["player"])
        if ref_player is None:
            raise NotImplementedError(
                f"Unrecognized player '{p['player']}' - ambiguity resolution not yet implemented"
            )
        resolved_players.append({**p, "ref_player": ref_player})

    primary_team_ids = {rp["ref_player"]["primary_team_id"] for rp in resolved_players}
    if len(primary_team_ids) != 1 or None in primary_team_ids:
        raise NotImplementedError(
            "Ambiguous or missing team assignment - not yet implemented"
        )

    return {"players": resolved_players, "ref_team_id": primary_team_ids.pop()}


def start_ingestion(pg_conn, turn_id, system_id, match_type, screenshot_ref, extracted_data):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pending_matches (turn_id, system_id, screenshot_ref, status, extracted_data)
            VALUES (%s, %s, %s, 'extracted', %s)
            RETURNING id
            """,
            (turn_id, system_id, screenshot_ref, json.dumps(extracted_data)),
        )
        pending_match_id = cur.fetchone()[0]
    pg_conn.commit()

    resolved = {
        faction: _resolve_faction(pg_conn, extracted_data["teams"][faction]["players"])
        for faction in ("imperial", "rebel")
    }

    team_id_by_faction = {
        faction: _get_or_create_team(pg_conn, resolved[faction]["ref_team_id"])
        for faction in ("imperial", "rebel")
    }

    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO matches (imperial_team_id, rebel_team_id, winner, match_type, turn_id, system_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                team_id_by_faction["imperial"],
                team_id_by_faction["rebel"],
                extracted_data["match_result"],
                match_type,
                turn_id,
                system_id,
            ),
        )
        match_id = cur.fetchone()[0]

        for faction, data in resolved.items():
            match_team_id = team_id_by_faction[faction]
            for rp in data["players"]:
                player_id = _get_or_create_player(
                    pg_conn, rp["player"], rp["ref_player"]["id"]
                )
                # data["ref_team_id"] is the single primary team every player in this
                # faction agreed on (enforced in _resolve_faction), so is_subbing is
                # always False in this slice; written generally for when partial
                # subbing is handled in a later slice.
                is_subbing = rp["ref_player"]["primary_team_id"] != data["ref_team_id"]
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
                        _player_hash(rp["player"]),
                        match_team_id,
                        faction.upper(),
                        rp["position"],
                        rp["ref_player"]["primary_role"],
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

    return {
        "status": "persisted",
        "match_id": match_id,
        "pending_match_id": pending_match_id,
    }
