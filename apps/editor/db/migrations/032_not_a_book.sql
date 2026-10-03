-- «Kitap değil» türü (editor/book_type.py NOT_A_BOOK, 2026-10-03 arşiv pilotu denetimi): yayınevi kataloğu, bülten,
-- broşür, fiyat listesi ya da yalnız kapak / çok az sayfalı dosya. Bir katalog %72 kurgu sayılmış, yazar/kitap adları
-- karakter, tanıtımlar olay olmuştu. Bu türde karakter, olay, duygu/tema okunmaz; kategori/yaş önerisi yapılmaz.
-- form_source yeni değer: RULE (sayfaların metninden kural; CHECK yok, yalnız belge).
SET search_path = ed, public;
ALTER TABLE book_profile DROP CONSTRAINT IF EXISTS book_profile_form_check;
ALTER TABLE book_profile ADD CONSTRAINT book_profile_form_check
  CHECK (form IN ('FICTION','NARRATIVE_NONFICTION','EXPOSITORY','ACTIVITY','POETRY','UNKNOWN','NOT_A_BOOK'));
