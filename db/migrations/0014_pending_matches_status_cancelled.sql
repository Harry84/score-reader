-- Adds a 'cancelled' terminal status: lets someone abandon a pending match
-- stuck on an awaiting_* pause (e.g. a bad screenshot that shouldn't be
-- confirmed past roster_size/missing_field validation) instead of it just
-- sitting unanswered forever with no way out. See
-- ingestion.workflow.cancel_ingestion. Terminal like 'persisted' - a
-- cancelled match can't be resumed; re-post the screenshot to try again.
ALTER TABLE pending_matches DROP CONSTRAINT pending_matches_status_valid;
ALTER TABLE pending_matches ADD CONSTRAINT pending_matches_status_valid CHECK (
    status IN ('extracted', 'ready', 'persisted', 'cancelled')
    OR status LIKE 'awaiting_player_match:%'
    OR status LIKE 'awaiting_team_assignment:%'
    OR status LIKE 'awaiting_roster_size:%'
    OR status LIKE 'awaiting_missing_field:%'
);
