-- Raw extraction output is kept alongside the workflow's accumulated answers,
-- so the ingestion workflow (Phase 1) can re-derive suggestions at any step
-- without re-running vision extraction.
ALTER TABLE pending_matches
    ADD COLUMN extracted_data JSONB NOT NULL DEFAULT '{}'::jsonb;
