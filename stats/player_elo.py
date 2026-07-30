"""Player ELO ladders for pickup/ranked matches: a "general" (base) ladder
plus three role-specific ladders (Flex/Support/Farmer), scoped per campaign
and match_type - pickup and ranked are always independent ladders (matching
the existing system's separate report files), and campaigns never share
ELO state (ADR-0007).

Ports stats_reader/player_elo_ladder.py (general ladder) and
stats_reader/role_elo_calculator.py (role ladders) combined into a single
pass over match history, rather than the original's two separate scripts
each independently recomputing the same general-rating progression.
"""

from stats_reader.elo_ladder import calculate_expected_outcome, calculate_new_rating

STARTING_ELO = 1000
K_FACTOR = 32
GENERAL = "general"
ROLES = ["Flex", "Support", "Farmer"]
ALL_LADDERS = [GENERAL] + ROLES


def recompute_player_elo(pg_conn, campaign_id, match_type, starting_elo=STARTING_ELO, k_factor=K_FACTOR):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id FROM players")
        player_ids = [row[0] for row in cur.fetchall()]

        cur.execute(
            """
            SELECT id FROM matches
            WHERE match_type = %s AND campaign_id = %s AND winner IN ('IMPERIAL', 'REBEL')
            ORDER BY match_date, id
            """,
            (match_type, campaign_id),
        )
        match_ids = [row[0] for row in cur.fetchall()]

        match_rosters = {}
        for match_id in match_ids:
            cur.execute(
                "SELECT player_id, faction, winner FROM player_stats ps JOIN matches m ON ps.match_id = m.id WHERE ps.match_id = %s",
                (match_id,),
            )
            match_rosters[match_id] = cur.fetchall()

        roles_by_match = {}
        if match_ids:
            cur.execute(
                "SELECT match_id, player_id, role FROM player_stats WHERE match_id = ANY(%s)",
                (match_ids,),
            )
            for match_id, player_id, role in cur.fetchall():
                roles_by_match.setdefault(match_id, {})[player_id] = role

    ratings = {ladder: {pid: float(starting_elo) for pid in player_ids} for ladder in ALL_LADDERS}
    played = {ladder: {} for ladder in ALL_LADDERS}
    won = {ladder: {} for ladder in ALL_LADDERS}
    lost = {ladder: {} for ladder in ALL_LADDERS}
    history_rows = []

    def _update(ladder, match_id, player_id, faction, expected, actual, winner):
        ratings[ladder].setdefault(player_id, float(starting_elo))
        old_rating = ratings[ladder][player_id]
        new_rating = calculate_new_rating(old_rating, expected, actual, k_factor)
        ratings[ladder][player_id] = new_rating
        played[ladder][player_id] = played[ladder].get(player_id, 0) + 1
        if actual == 1.0:
            won[ladder][player_id] = won[ladder].get(player_id, 0) + 1
        else:
            lost[ladder][player_id] = lost[ladder].get(player_id, 0) + 1
        history_rows.append((match_id, ladder, player_id, faction, old_rating, new_rating, winner))

    for match_id in match_ids:
        roster = match_rosters[match_id]
        imperial = [(pid, faction) for pid, faction, _winner in roster if faction == "IMPERIAL"]
        rebel = [(pid, faction) for pid, faction, _winner in roster if faction == "REBEL"]
        if not imperial or not rebel:
            continue
        winner = roster[0][2]

        for pid, _ in imperial + rebel:
            ratings[GENERAL].setdefault(pid, float(starting_elo))

        imperial_avg = sum(ratings[GENERAL][pid] for pid, _ in imperial) / len(imperial)
        rebel_avg = sum(ratings[GENERAL][pid] for pid, _ in rebel) / len(rebel)

        imperial_expected = calculate_expected_outcome(imperial_avg, rebel_avg)
        rebel_expected = 1.0 - imperial_expected
        imperial_actual = 1.0 if winner == "IMPERIAL" else 0.0
        rebel_actual = 1.0 - imperial_actual

        player_roles = roles_by_match.get(match_id, {})

        for pid, faction in imperial:
            _update(GENERAL, match_id, pid, faction, imperial_expected, imperial_actual, winner)
            role = player_roles.get(pid)
            if role in ROLES:
                _update(role, match_id, pid, faction, imperial_expected, imperial_actual, winner)

        for pid, faction in rebel:
            _update(GENERAL, match_id, pid, faction, rebel_expected, rebel_actual, winner)
            role = player_roles.get(pid)
            if role in ROLES:
                _update(role, match_id, pid, faction, rebel_expected, rebel_actual, winner)

    ladders = {}
    for ladder in ALL_LADDERS:
        entries = [
            {
                "player_id": pid,
                "rating": rating,
                "matches_played": played[ladder].get(pid, 0),
                "matches_won": won[ladder].get(pid, 0),
                "matches_lost": lost[ladder].get(pid, 0),
            }
            for pid, rating in ratings[ladder].items()
            if played[ladder].get(pid, 0) > 0
        ]
        entries.sort(key=lambda row: row["rating"], reverse=True)
        for rank, row in enumerate(entries, start=1):
            row["rank"] = rank
        ladders[ladder] = entries

    with pg_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM player_elo_history WHERE campaign_id = %s AND match_type = %s",
            (campaign_id, match_type),
        )
        cur.execute(
            "DELETE FROM player_elo_ratings WHERE campaign_id = %s AND match_type = %s",
            (campaign_id, match_type),
        )

        for ladder, entries in ladders.items():
            for row in entries:
                cur.execute(
                    """
                    INSERT INTO player_elo_ratings
                        (player_id, campaign_id, match_type, role, rating,
                         matches_played, matches_won, matches_lost, rank)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        row["player_id"],
                        campaign_id,
                        match_type,
                        ladder,
                        row["rating"],
                        row["matches_played"],
                        row["matches_won"],
                        row["matches_lost"],
                        row["rank"],
                    ),
                )

        for match_id, ladder, player_id, faction, old_rating, new_rating, winner in history_rows:
            cur.execute(
                """
                INSERT INTO player_elo_history
                    (match_id, campaign_id, match_type, role, player_id, faction,
                     old_rating, new_rating, winner)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (match_id, campaign_id, match_type, ladder, player_id, faction, old_rating, new_rating, winner),
            )
    pg_conn.commit()

    return ladders
