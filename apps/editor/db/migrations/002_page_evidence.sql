-- Pixel-level facts about a page and the role a page plays in the book.
-- Both are book-independent mechanisms (no book-specific rule lives in code).
SET search_path = ed, public;

-- Share of the page body that carries ink outside visible text lines.
-- ~0 means there is nothing to look at: no vision model is asked about it.
ALTER TABLE page ADD COLUMN nontext_ink real;

-- STORY pages feed events/emotions/timeline; the rest (front matter, reader
-- activities, informational inserts) are kept searchable but are not story.
CREATE TABLE page_role (
  generation_id uuid NOT NULL REFERENCES generation(id),
  page_no      int NOT NULL,
  role         text NOT NULL CHECK (role IN ('STORY','FRONT_MATTER','NON_STORY')),
  source       text NOT NULL,               -- 'layout' | 'extract'
  model_call_id bigint REFERENCES model_call(id),
  PRIMARY KEY (generation_id, page_no)
);
