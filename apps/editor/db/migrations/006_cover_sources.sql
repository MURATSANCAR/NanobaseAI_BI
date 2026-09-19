-- Cover sources and their priority: UPLOADED (an editor chose it) > CRM (newest dated
-- image of the matched CRM book) > WEB (product image on the publisher's site, page
-- matched by ISBN) > PDF_PAGE (stand-in).
SET search_path = ed, public;
ALTER TABLE book_cover DROP CONSTRAINT book_cover_source_check;
ALTER TABLE book_cover ADD CONSTRAINT book_cover_source_check CHECK (source IN ('UPLOADED','CRM','WEB','PDF_PAGE'));
ALTER TABLE book_cover ADD COLUMN source_date timestamptz;      -- date of the image at its source
ALTER TABLE book_cover ADD COLUMN source_ref  jsonb NOT NULL DEFAULT '{}';  -- crm ids, path, how it was matched

-- What the CRM connector found for a book (kept even when no file could be fetched,
-- so the UI can say why a book has no CRM cover).
CREATE TABLE cover_lookup (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id      uuid NOT NULL REFERENCES book(id),
  matched_by   text,                          -- ISBN | TITLE | NONE
  crm_book_id  text,
  crm_title    text,
  candidates   jsonb NOT NULL DEFAULT '[]',   -- [{kind, path, date, name}]
  chosen       jsonb,
  source       text NOT NULL DEFAULT 'CRM',   -- CRM | WEB
  outcome      text NOT NULL,                 -- STORED | NO_MATCH | NO_IMAGE | FETCH_FAILED | AMBIGUOUS
  detail       text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
