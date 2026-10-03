"""Team ELO ladder, recomputed from scratch on each 'team' Match persist,
scoped per campaign (ADR-0007) - each campaign gets its own ladder/history,
reset to the starting ELO, rather than one continuous ladder across all
campaigns.

Matches stats_reader.elo_ladder's existing behavior of always replaying the
full match history rather than updating incrementally (see
ELO_LADDER_README.md), now writing to Postgres tables instead of JSON files
(ADR-0003) so the Phase 3 read API can serve them directly.
"""

from stats_reader.elo_ladder import calculate_expected_outcome, calculate_new_rating

STARTING_ELO = 1000
K_FACTOR = 32


def recompute_team_elo(pg_conn, campaign_id, starting_elo=STARTING_ELO, k_factor=K_FACTOR):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT id FROM teams")
        team_ids = [row[0] for row in cur.fetchall()]

        cur.execute(
            """
            SELECT id, imperial_team_id, rebel_team_id, winner
            FROM matches
            WHERE match_type = 'team' AND campaign_id = %s AND winner IN ('IMPERIAL', 'REBEL')
            ORDER BY match_date, id
            """,
            (campaign_id,),
        )
        matches = cur.fetchall()

    ratings = {team_id: float(starting_elo) for team_id in team_ids}
    played = {team_id: 0 for team_id in team_ids}
    won = {team_id: 0 for team_id in team_ids}
    lost = {team_id: 0 for team_id in team_ids}
    history_rows = []

    for match_id, imperial_id, rebel_id, winner in matches:
        imperial_rating = ratings.setdefault(imperial_id, float(starting_elo))
        rebel_rating = ratings.setdefault(rebel_id, float(starting_elo))

        imperial_expected = calculate_expected_outcome(imperial_rating, rebel_rating)
        rebel_expected = 1.0 - imperial_expected
        imperial_actual = 1.0 if winner == "IMPERIAL" else 0.0
        rebel_actual = 1.0 - imperial_actual

        new_imperial_rating = calculate_new_rating(
            imperial_rating, imperial_expected, imperial_actual, k_factor
        )
        new_rebel_rating = calculate_new_rating(
            rebel_rating, rebel_expected, rebel_actual, k_factor
        )

        history_rows.append(
            (
                match_id,
                imperial_id,
                rebel_id,
                imperial_rating,
                new_imperial_rating,
                rebel_rating,
                new_rebel_rating,
                winner,
            )
        )

        ratings[imperial_id] = new_imperial_rating
        ratings[rebel_id] = new_rebel_rating
        played[imperial_id] = played.get(imperial_id, 0) + 1
        played[rebel_id] = played.get(rebel_id, 0) + 1
        if winner == "IMPERIAL":
            won[imperial_id] = won.get(imperial_id, 0) + 1
            lost[rebel_id] = lost.get(rebel_id, 0) + 1
        else:
            won[rebel_id] = won.get(rebel_id, 0) + 1
            lost[imperial_id] = lost.get(imperial_id, 0) + 1

    ladder = sorted(
        (
            {
                "team_id": team_id,
                "rating": rating,
                "matches_played": played.get(team_id, 0),
                "matches_won": won.get(team_id, 0),
                "matches_lost": lost.get(team_id, 0),
            }
            for team_id, rating in ratings.items()
        ),
        key=lambda row: row["rating"],
        reverse=True,
    )

    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM team_elo_history WHERE campaign_id = %s", (campaign_id,))
        cur.execute("DELETE FROM team_elo_ratings WHERE campaign_id = %s", (campaign_id,))

        for rank, row in enumerate(ladder, start=1):
            cur.execute(
                """
                INSERT INTO team_elo_ratings
                    (team_id, campaign_id, rating, matches_played, matches_won, matches_lost, rank)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["team_id"],
                    campaign_id,
                    row["rating"],
                    row["matches_played"],
                    row["matches_won"],
                    row["matches_lost"],
                    rank,
                ),
            )

        for history_row in history_rows:
            cur.execute(
                """
                INSERT INTO team_elo_history
                    (match_id, imperial_team_id, rebel_team_id, imperial_old_rating,
                     imperial_new_rating, rebel_old_rating, rebel_new_rating, winner, campaign_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                history_row + (campaign_id,),
            )
    pg_conn.commit()


def get_team_elo_ladder(pg_conn, campaign_id):
    """ROADMAP Phase 5: the campaign project's team ELO ladder read."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.name, e.rating, e.matches_played, e.matches_won, e.matches_lost, e.rank
            FROM team_elo_ratings e JOIN teams t ON t.id = e.team_id
            WHERE e.campaign_id = %s
            ORDER BY e.rank
            """,
            (campaign_id,),
        )
        rows = cur.fetchall()
    return [
        {
            "team_id": r[0],
            "name": r[1],
            "rating": float(r[2]),
            "matches_played": r[3],
            "matches_won": r[4],
            "matches_lost": r[5],
            "rank": r[6],
        }
        for r in rows
    ]
