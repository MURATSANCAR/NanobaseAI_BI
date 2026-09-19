-- A claim the application repaired itself (added evidence or narrowed) is kept,
-- marked SUPERSEDED, and replaced by a new claim (claims are immutable).
SET search_path = ed, public;
ALTER TABLE claim DROP CONSTRAINT claim_status_check;
ALTER TABLE claim ADD CONSTRAINT claim_status_check CHECK (status IN (
  'CANDIDATE','VERIFIED','NEEDS_REVIEW','REJECTED','SUPERSEDED',
  'EDITOR_APPROVED','EDITOR_REJECTED','EDITOR_CORRECTED'));
