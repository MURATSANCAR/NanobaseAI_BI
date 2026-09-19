-- Catalog: one card per analysed book, built only from verified ledger claims of
-- the book's latest sealed generation; cover images; bibliographic metadata claims.
SET search_path = ed, public;

ALTER TABLE claim DROP CONSTRAINT claim_kind_check;
ALTER TABLE claim ADD CONSTRAINT claim_kind_check CHECK (kind IN (
  'CHARACTER','CHARACTER_IDENTITY','EVENT','EMOTION','THEME','SUMMARY','VISUAL_SCENE',
  'VISUAL_CONTINUITY','TEXT_VISUAL_MISMATCH','CANON','AGE_GROUP','PUBLISHER_DECISION','ANSWER',
  'METADATA'));

-- An uploaded cover always wins over a page picked from the PDF.
CREATE TABLE book_cover (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id      uuid NOT NULL REFERENCES book(id),
  source       text NOT NULL CHECK (source IN ('UPLOADED','PDF_PAGE')),
  file_path    text NOT NULL,
  page_no      int,                          -- for PDF_PAGE
  sha256       text,
  width_px     int,
  height_px    int,
  added_by     text NOT NULL,
  is_current   boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX book_cover_current ON book_cover(book_id) WHERE is_current;

CREATE TABLE book_card (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id      uuid NOT NULL REFERENCES book(id),
  book_version_id uuid NOT NULL REFERENCES book_version(id),
  generation_id uuid NOT NULL REFERENCES generation(id),
  title        text NOT NULL,
  metadata     jsonb NOT NULL DEFAULT '{}',  -- field -> {value, page, quote, claim_id}
  age_min      int,
  age_max      int,
  summary      jsonb NOT NULL DEFAULT '[]',  -- [{text, pages, claim_id}]
  themes       jsonb NOT NULL DEFAULT '[]',  -- [{theme, text, pages, claim_id}]
  characters   jsonb NOT NULL DEFAULT '[]',  -- [{name, aliases, description}]
  key_events   jsonb NOT NULL DEFAULT '[]',  -- [{role, text, pages, claim_id}]
  card_text    text NOT NULL,
  is_current   boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX book_card_current ON book_card(book_id) WHERE is_current;
