-- Adds two extraction-validation pauses (ROADMAP Phase 3): a faction with
-- other than EXPECTED_ROSTER_SIZE players (awaiting_roster_size:<faction>)
-- and a player record missing a required field (awaiting_missing_field:
-- <player>:<field>). Drops awaiting_role:%, which ingestion/workflow.py no
-- longer produces (a missing role is now a legitimate persisted state,
-- fixable via edit_match_player instead of pausing) - tidying the stale
-- constraint entry per the loose-ends note the last time this was touched.
ALTER TABLE pending_matches DROP CONSTRAINT pending_matches_status_valid;
ALTER TABLE pending_matches ADD CONSTRAINT pending_matches_status_valid CHECK (
    status IN ('extracted', 'ready', 'persisted')
    OR status LIKE 'awaiting_player_match:%'
    OR status LIKE 'awaiting_team_assignment:%'
    OR status LIKE 'awaiting_roster_size:%'
    OR status LIKE 'awaiting_missing_field:%'
);
