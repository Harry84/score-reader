-- Duplicate-ingestion guard: a canonical fingerprint of a match's actual
-- stats (ingestion.workflow._compute_stats_hash), used to reject re-posting
-- the same screenshot as a second Match. Scoped per campaign_id via the
-- index below, not a unique constraint - the check that enforces this is
-- application-level (start_ingestion raises DuplicateMatchError before any
-- pending_matches row is created), a hard stop with no confirm-to-override
-- path, unlike the awaiting_roster_size/awaiting_missing_field pauses.
-- Existing rows are left with stats_hash NULL rather than backfilled (NULL
-- never equality-matches, so pre-migration matches are simply never
-- flagged as duplicates - not worth reconstructing from already-curated
-- pre-DB historical data).
ALTER TABLE matches ADD COLUMN stats_hash TEXT;
CREATE INDEX idx_matches_campaign_stats_hash ON matches (campaign_id, stats_hash);
