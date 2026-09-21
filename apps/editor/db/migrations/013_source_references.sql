SET search_path=ed,public;
-- Null source_refs identifies historical paragraph indices. New references name
-- the reading policy and immutable original-source offsets; no legacy rows change.
ALTER TABLE evidence ADD COLUMN source_refs jsonb;
