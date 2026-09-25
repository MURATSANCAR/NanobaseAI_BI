-- The publisher serves every kind of book (user decision 2026-09-24): novels, history,
-- psychology, activity books, poetry — not only illustrated children's stories. What kind of
-- book it is decides which steps mean anything (docs/TUM-KITAP-TURLERI-ANALIZ.md).
SET search_path = ed, public;

-- The publisher's own classification, as the CRM stock card holds it (new_kitapBase):
-- new_hedefkitle 1/2/3 -> CHILD/YOUNG/ADULT, new_turlertext (comma separated),
-- new_webkategorilertext, the weighted target age range, the planned page count.
ALTER TABLE book_crm_record
  ADD COLUMN IF NOT EXISTS audience       text,               -- CHILD | YOUNG | ADULT
  ADD COLUMN IF NOT EXISTS genres         jsonb NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS web_categories text,
  ADD COLUMN IF NOT EXISTS age_from       int,
  ADD COLUMN IF NOT EXISTS age_to         int,
  ADD COLUMN IF NOT EXISTS page_count     int;

-- What kind of book one generation read, and where that came from. One row per generation:
-- a new CRM record or an editor's answer applies to the next reading, never silently to a
-- sealed one.
--   form      FICTION | NARRATIVE_NONFICTION | EXPOSITORY | ACTIVITY | POETRY | UNKNOWN
--   audience  CHILD | YOUNG | ADULT | UNKNOWN
CREATE TABLE IF NOT EXISTS book_profile (
  generation_id     uuid PRIMARY KEY REFERENCES generation(id) ON DELETE CASCADE,
  form              text NOT NULL,
  form_source       text NOT NULL,        -- CRM | MODEL | EDITOR | NONE
  form_detail       jsonb NOT NULL DEFAULT '{}',   -- CRM genres and their forms, model probabilities
  audience          text NOT NULL,
  audience_source   text NOT NULL,        -- CRM | EDITOR | NONE
  age_from          int,
  age_to            int,
  illustrated_pages int NOT NULL,
  pages             int NOT NULL,
  model_call_id     bigint,
  created_at        timestamptz NOT NULL DEFAULT now(),
  CHECK (form IN ('FICTION','NARRATIVE_NONFICTION','EXPOSITORY','ACTIVITY','POETRY','UNKNOWN')),
  CHECK (audience IN ('CHILD','YOUNG','ADULT','UNKNOWN'))
);
