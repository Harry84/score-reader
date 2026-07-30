-- ADR-0007: campaign_id as an opaque reference, matching how turn_id is
-- already treated. Nullable on matches (historical pre-campaign data has no
-- meaningful value); required on pending_matches, which only ever holds
-- rows from this project's own ingestion workflow.
ALTER TABLE matches ADD COLUMN campaign_id TEXT;

ALTER TABLE pending_matches ADD COLUMN campaign_id TEXT NOT NULL DEFAULT '';
ALTER TABLE pending_matches ALTER COLUMN campaign_id DROP DEFAULT;

-- Team ELO becomes campaign-scoped: each campaign gets its own ladder and
-- history rather than one continuous ladder across all campaigns. Existing
-- rows are fully derived/recomputed data with no meaningful campaign_id, so
-- they're cleared rather than backfilled - recompute_team_elo regenerates
-- them from matches on the next persist.
DELETE FROM team_elo_history;
DELETE FROM team_elo_ratings;

ALTER TABLE team_elo_ratings DROP CONSTRAINT team_elo_ratings_pkey;
ALTER TABLE team_elo_ratings ADD COLUMN campaign_id TEXT NOT NULL;
ALTER TABLE team_elo_ratings ADD PRIMARY KEY (team_id, campaign_id);

ALTER TABLE team_elo_history ADD COLUMN campaign_id TEXT NOT NULL;
