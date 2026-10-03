-- Kitap adının kaynağına CRM (editor/book_title.py, kullanıcı kararı 2026-10-03: «CRM baz al, yoksa timas.com.tr»).
-- Öncelik: user > crm > site > metadata > file.
SET search_path = ed, public;
ALTER TABLE book DROP CONSTRAINT IF EXISTS book_title_source_check;
ALTER TABLE book ADD CONSTRAINT book_title_source_check
  CHECK (title_source IS NULL OR title_source IN ('user','crm','site','metadata','file'));
