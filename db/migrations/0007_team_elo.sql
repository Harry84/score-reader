-- Team ELO ladder + history, recomputed from scratch on each 'team' Match
-- persist (synchronous, per the agreed ELO recompute timing). Replaces the
-- JSON-file output of stats_reader.elo_ladder with queryable Postgres
-- tables, matching ADR-0003's move away from SQLite/file-based reports.
CREATE TABLE team_elo_ratings (
    team_id INTEGER PRIMARY KEY REFERENCES teams(id),
    rating NUMERIC NOT NULL,
    matches_played INTEGER NOT NULL,
    matches_won INTEGER NOT NULL,
    matches_lost INTEGER NOT NULL,
    rank INTEGER NOT NULL
);

CREATE TABLE team_elo_history (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    imperial_team_id INTEGER NOT NULL REFERENCES teams(id),
    rebel_team_id INTEGER NOT NULL REFERENCES teams(id),
    imperial_old_rating NUMERIC NOT NULL,
    imperial_new_rating NUMERIC NOT NULL,
    rebel_old_rating NUMERIC NOT NULL,
    rebel_new_rating NUMERIC NOT NULL,
    winner TEXT NOT NULL
);
