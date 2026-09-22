-- What the publisher's CRM says about a book (connectors/crm_covers.py): authors, the
-- summary text, ISBN, stock code, first publication date. Kept apart from the book's
-- verified claims: the card shows it labelled as the publisher's record, it never becomes
-- evidence. One current row per book; a later lookup that no longer matches removes it.
SET search_path = ed, public;
CREATE TABLE IF NOT EXISTS book_crm_record (
  book_id            uuid PRIMARY KEY REFERENCES book(id),
  crm_book_id        text NOT NULL,
  crm_project_id     text,
  matched_by         text NOT NULL,          -- ISBN | TITLE | PARTIAL, optionally +EDITIONS
  crm_title          text NOT NULL,
  authors            jsonb NOT NULL DEFAULT '[]',
  illustrators       jsonb NOT NULL DEFAULT '[]',
  summary            text,
  summary_field      text,                   -- which CRM field the summary came from
  isbn               text,
  stock_code         text,
  first_publish_date date,
  crm_modified_on    timestamptz,
  synced_at          timestamptz NOT NULL DEFAULT now()
);
