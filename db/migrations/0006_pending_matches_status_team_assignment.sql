-- Adds the awaiting_team_assignment:<faction> step, hit when a faction's
-- players have no clear-majority primary team to infer the match team from.
-- Drops awaiting_subbing:%: subbing turned out not to need its own pause -
-- it's auto-computed once team assignment is resolved (majority vote, or
-- this new override), same as awaiting_match_type didn't end up needed.
ALTER TABLE pending_matches DROP CONSTRAINT pending_matches_status_valid;
ALTER TABLE pending_matches ADD CONSTRAINT pending_matches_status_valid CHECK (
    status IN ('extracted', 'ready', 'persisted')
    OR status LIKE 'awaiting_player_match:%'
    OR status LIKE 'awaiting_team_assignment:%'
    OR status LIKE 'awaiting_role:%'
);
