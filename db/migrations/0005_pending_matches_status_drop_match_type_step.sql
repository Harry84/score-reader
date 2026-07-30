-- awaiting_match_type was in the original ADR-0005 sketch, but match_type
-- turned out to be a required ingestion input (the score bot always knows
-- it from context), not an ambiguous workflow step. Tighten the constraint
-- to match what the workflow actually produces.
ALTER TABLE pending_matches DROP CONSTRAINT pending_matches_status_valid;
ALTER TABLE pending_matches ADD CONSTRAINT pending_matches_status_valid CHECK (
    status IN ('extracted', 'ready', 'persisted')
    OR status LIKE 'awaiting_player_match:%'
    OR status LIKE 'awaiting_subbing:%'
    OR status LIKE 'awaiting_role:%'
);
