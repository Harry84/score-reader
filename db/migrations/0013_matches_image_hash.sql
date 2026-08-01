-- Cheaper, earlier duplicate-ingestion guard alongside 0012's stats_hash:
-- a hash of the raw screenshot bytes, checked in api/main.py *before*
-- calling the (paid) Claude vision API at all - catches a byte-for-byte
-- repeat upload without needing to re-extract it first. Narrower than
-- stats_hash (won't catch a second genuine screenshot of the same result
-- screen, since the image bytes differ even if the stats don't), so both
-- checks stay in place rather than replacing one with the other.
-- pending_matches carries the precomputed hash from ingestion.workflow.
-- check_duplicate_image through to _persist, since a pending_matches row
-- can outlive the original request across awaiting_* pauses.
ALTER TABLE matches ADD COLUMN image_hash TEXT;
CREATE INDEX idx_matches_campaign_image_hash ON matches (campaign_id, image_hash);

ALTER TABLE pending_matches ADD COLUMN image_hash TEXT;
