-- match_type is a required ingestion input (ROADMAP Phase 1), not an
-- ambiguous step, but must be persisted so submit_answer can resume the
-- workflow without the caller re-supplying it.
ALTER TABLE pending_matches
    ADD COLUMN match_type TEXT NOT NULL DEFAULT 'team';
ALTER TABLE pending_matches
    ALTER COLUMN match_type DROP DEFAULT;
