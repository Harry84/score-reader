-- A team's campaign faction (IMPERIAL-MIRROR-BUILD-PLAN.md, Dynamic Trust
-- Alignment repo): nullable, no default -- existing rows stay NULL, which
-- the campaign project treats as "rebel" (today's implicit assumption,
-- made explicit downstream rather than backfilled here). Lowercase
-- 'rebel'/'imperial', matching that project's own FACTIONS tuple, not the
-- uppercase REBEL/IMPERIAL used elsewhere in this repo for match winners.
ALTER TABLE ref_teams ADD COLUMN faction TEXT;
