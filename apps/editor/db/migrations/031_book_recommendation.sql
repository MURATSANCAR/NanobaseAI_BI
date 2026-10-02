-- Kategori ve yaş önerisi (editor/recommend.py, kullanıcı kararı 2026-10-02): arşiv kipinde okunan kitabın içeriğinden
-- Zeki AI'ın önerdiği kategori (yayınevi sitesinin kategori ağacından bir yol), okur kitlesi, yaş aralığı, güven ve
-- gerekçe. Yalnız öneri: kitabın profili (book_profile) değişmez, karar editörde. Sitedeki kategori burada tutulmaz,
-- okunurken cover_library'den eşlenir. Nesil başına bir satır.
SET search_path = ed, public;
CREATE TABLE IF NOT EXISTS book_recommendation (
  generation_id   uuid PRIMARY KEY REFERENCES generation(id) ON DELETE CASCADE,
  status          text NOT NULL,                    -- OK | NO_TEXT | NO_TREE | FAILED
  category        jsonb NOT NULL DEFAULT '[]',      -- site kategori yolu, kökten yaprağa
  audience        text,                             -- CHILD | YOUNG | ADULT
  age_from        int,
  age_to          int,                              -- NULL: üst sınır yok
  confidence      text,                             -- HIGH | MEDIUM | LOW
  reason          text,
  evidence_pages  int[] NOT NULL DEFAULT '{}',
  tree_digest     text,                             -- istemdeki kategori listesinin özeti
  input           jsonb NOT NULL DEFAULT '{}',      -- modele giden girdi (denetim için)
  model_call_id   bigint,
  error           text,
  version         text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('OK','NO_TEXT','NO_TREE','FAILED')),
  CHECK (audience IS NULL OR audience IN ('CHILD','YOUNG','ADULT')),
  CHECK (confidence IS NULL OR confidence IN ('HIGH','MEDIUM','LOW'))
);
