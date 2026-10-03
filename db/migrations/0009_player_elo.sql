-- Player ELO ladders for pickup/ranked matches: a "general" (base) ladder
-- plus three role-specific ladders (Flex/Support/Farmer), combined into one
-- pair of tables keyed by role ('general' for the base ladder), rather than
-- separate tables per ladder. Scoped per campaign and match_type (pickup
-- and ranked are always independent ladders, matching the existing
-- system's separate pickup_*/ranked_* report files), same campaign-scoping
-- pattern as team_elo (ADR-0007).
CREATE TABLE player_elo_ratings (
    player_id INTEGER NOT NULL REFERENCES players(id),
    campaign_id TEXT NOT NULL,
    match_type TEXT NOT NULL,
    role TEXT NOT NULL,
    rating NUMERIC NOT NULL,
    matches_played INTEGER NOT NULL,
    matches_won INTEGER NOT NULL,
    matches_lost INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    PRIMARY KEY (player_id, campaign_id, match_type, role)
);

CREATE TABLE player_elo_history (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id),
    campaign_id TEXT NOT NULL,
    match_type TEXT NOT NULL,
    role TEXT NOT NULL,
    player_id INTEGER NOT NULL REFERENCES players(id),
    faction TEXT NOT NULL,
    old_rating NUMERIC NOT NULL,
    new_rating NUMERIC NOT NULL,
    winner TEXT NOT NULL
);
