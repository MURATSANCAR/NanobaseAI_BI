-- Traits the TEXT declares about a character (sex, age band). They tell two characters of
-- the same kind apart, so a lone drawn figure can still become a reference when the only
-- rival named nearby is of the other sex or another age band.
SET search_path = ed, public;
ALTER TABLE character ADD COLUMN traits jsonb NOT NULL DEFAULT '{}';
