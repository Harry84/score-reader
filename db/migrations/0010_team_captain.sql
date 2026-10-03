-- Captain-of-team (ADR-0008): backend-verified authorization for roster
-- changes, independent of whatever the calling Discord bot asserts.
ALTER TABLE ref_teams ADD COLUMN captain_discord_id TEXT;
