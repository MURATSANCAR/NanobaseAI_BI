-- A review item raised by the reading of a book whose kind does not fit the reading's premise
-- (editor.book_type: a book that tells no story read for characters, events, modality and
-- who-did-what) is advice, not a question the editor must close: the user decided on
-- 2026-09-24 that every book is read in full and what does not fit is shown as advice. It stays
-- OPEN — the editor can still answer it — but no readiness gate counts it.
SET search_path = ed, public;
ALTER TABLE review_item ADD COLUMN IF NOT EXISTS advisory boolean NOT NULL DEFAULT false;
