-- Kapak arşivi (production/library.py): yayınevinin yayımlanmış kitap kapakları, sitedeki kategori yoluyla.
-- Köprü besler (T-soft ürünü + barkodla bağlı CRM kitap kartı); görseli stüdyo kendisi indirir. Kitabın
-- kanıt defterinden ayrıdır, hiçbir iddiaya kanıt olmaz: yalnız tasarımcının göz attığı ve ileride istem
-- kütüphanesinin referans aldığı arşiv. Kayıt silinmez; satıştan kalkan kitabın kapağı da arşivde kalır.
SET search_path = ed, public;
CREATE TABLE IF NOT EXISTS cover_library (
  id            text PRIMARY KEY,               -- kaynak + kaynaktaki kimlik (ör. tsoft-12345)
  source        text NOT NULL,                  -- tsoft
  source_id     text NOT NULL,
  title         text NOT NULL,
  authors       jsonb NOT NULL DEFAULT '[]',
  illustrators  jsonb NOT NULL DEFAULT '[]',
  isbn          text,
  brand         text,                           -- yayınevi / marka (Timaş, Timaş Çocuk, …)
  category      jsonb NOT NULL DEFAULT '[]',    -- sitedeki varsayılan kategori yolu, kökten yaprağa
  categories    jsonb NOT NULL DEFAULT '[]',    -- ürünün bağlı olduğu bütün kategori yolları
  audience      text,                           -- CRM okur kitlesi: CHILD | YOUNG | ADULT
  age_from      int,
  age_to        int,
  genres        jsonb NOT NULL DEFAULT '[]',    -- CRM türleri
  on_sale       boolean NOT NULL DEFAULT true,
  sales         int NOT NULL DEFAULT 0,          -- sitedeki toplam satış (sıralama için)
  page_url      text,
  image_url     text,                           -- kaynağın en büyük kapak görseli
  image_file    text,                           -- storage/library/covers altındaki dosya adı
  image_sha     text,
  image_w       int,
  image_h       int,
  status        text NOT NULL DEFAULT 'pending', -- pending | ok | failed | none (görsel adresi yok)
  error         text,
  fetched_at    timestamptz,
  source_seen   timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS cover_library_source ON cover_library (source, source_id);
CREATE INDEX IF NOT EXISTS cover_library_status ON cover_library (status);
