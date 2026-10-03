-- Kitap adının kaynağı (editor/book_title.py, kullanıcı kararı 2026-10-03). Öncelik: kişinin verdiği ad (user) >
-- yayınevi sitesindeki ürün adı (site) > künyedeki ad (metadata) > temizlenmiş dosya adı (file). Otomatik çözüm
-- kişinin adını hiç ezmez. NULL: bu kuraldan önce açılmış kayıt (tek seferlik `python -m editor.book_title fix`).
SET search_path = ed, public;
ALTER TABLE book ADD COLUMN IF NOT EXISTS title_source text;
ALTER TABLE book ADD COLUMN IF NOT EXISTS title_review text[] NOT NULL DEFAULT '{}';  -- gözden geçirme nedenleri
ALTER TABLE book ADD COLUMN IF NOT EXISTS title_file text;                             -- adın türediği özgün dosya adı
DO $$ BEGIN
  ALTER TABLE book ADD CONSTRAINT book_title_source_check
    CHECK (title_source IS NULL OR title_source IN ('user','site','metadata','file'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
