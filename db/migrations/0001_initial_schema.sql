-- Initial schema: ports the existing SQLite tables to Postgres (ADR-0003),
-- and adds turn_id/system_id on matches, the systems lookup, and
-- pending_matches for the ingestion workflow (ADR-0005).

CREATE TABLE seasons (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Small, hand-seeded lookup of the campaign's fixed system map (CONTEXT.md: System).
CREATE TABLE systems (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    reference_id INTEGER,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ref_teams (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    alias TEXT
);

CREATE TABLE ref_players (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    primary_team_id INTEGER REFERENCES ref_teams(id),
    primary_role TEXT,
    alias TEXT,
    source_file TEXT
);

ALTER TABLE teams
    ADD CONSTRAINT teams_reference_id_fkey
    FOREIGN KEY (reference_id) REFERENCES ref_teams(id);

CREATE TABLE matches (
    id SERIAL PRIMARY KEY,
    season_id INTEGER REFERENCES seasons(id),
    match_date TIMESTAMPTZ NOT NULL DEFAULT now(),
    imperial_team_id INTEGER REFERENCES teams(id),
    rebel_team_id INTEGER REFERENCES teams(id),
    winner TEXT,
    filename TEXT,
    match_type TEXT,
    turn_id TEXT,
    system_id INTEGER REFERENCES systems(id)
);

CREATE TABLE players (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    reference_id INTEGER REFERENCES ref_players(id),
    player_hash TEXT UNIQUE
);

CREATE TABLE player_stats (
    id SERIAL PRIMARY KEY,
    match_id INTEGER REFERENCES matches(id),
    player_id INTEGER REFERENCES players(id),
    player_name TEXT,
    player_hash TEXT,
    team_id INTEGER REFERENCES teams(id),
    faction TEXT,
    position TEXT,
    role TEXT,
    score INTEGER,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    ai_kills INTEGER,
    cap_ship_damage INTEGER,
    is_subbing BOOLEAN NOT NULL DEFAULT false
);

-- Durable ingestion workflow state (ADR-0005). status is either one of the
-- fixed step names or "awaiting_<step>:<subject>" for per-player steps.
CREATE TABLE pending_matches (
    id SERIAL PRIMARY KEY,
    turn_id TEXT NOT NULL,
    system_id INTEGER NOT NULL REFERENCES systems(id),
    screenshot_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    answers JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pending_matches_status_valid CHECK (
        status IN ('extracted', 'awaiting_match_type', 'ready', 'persisted')
        OR status LIKE 'awaiting_player_match:%'
        OR status LIKE 'awaiting_subbing:%'
        OR status LIKE 'awaiting_role:%'
    )
);
