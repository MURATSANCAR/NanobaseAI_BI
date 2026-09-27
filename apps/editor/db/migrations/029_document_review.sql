-- Belge incelemesi: editörün Son Okuma ekranından yüklediği belge (doc, docx, pdf, odt, rtf, txt, md) üstünde
-- Zeki AI'ın metin denetimleri (kelime tekrarı, tik sözcük, cümle başı, kalıp ifade, yabancı/yaşa ağır sözcük).
-- Kitap okuması (generation) DEĞİLDİR: resim, karakter, olay okunmaz; bu yüzden son okuma tablolarından
-- (proof_run/proof_finding generation'a bağlı) ayrı tutulur. Belge metni çıkarılıp sayfalanmış hâliyle saklanır
-- (`pages`: source.read biçimi); özgün dosya saklanmaz. Kuyruk: status QUEUED → RUNNING → DONE | FAILED,
-- tüketici `python -m editor.document_review consume` (compose servisi document-review).
SET search_path = ed, public;

CREATE TABLE document_review (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title        text NOT NULL,
  file_name    text NOT NULL,
  format       text NOT NULL,                      -- pdf | docx | doc | odt | rtf | txt | md
  byte_size    integer NOT NULL,
  sha256       text NOT NULL,
  audience     text CHECK (audience IN ('CHILD','YOUNG','ADULT')),   -- yükleyenin beyanı; boş = bilinmiyor
  age_from     integer,
  age_to       integer,
  uploaded_by  text NOT NULL,
  pages        jsonb NOT NULL,                     -- [{page_no, approximate, spans:[{idx, text, source}]}]
  page_kind    text NOT NULL CHECK (page_kind IN ('PRINTED','APPROXIMATE')),
  words        integer NOT NULL,
  status       text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','RUNNING','DONE','FAILED')),
  error        text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  started_at   timestamptz,
  finished_at  timestamptz
);
CREATE INDEX document_review_queue ON document_review(status, created_at);
CREATE INDEX document_review_user ON document_review(uploaded_by, created_at DESC);

CREATE TABLE document_run (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id   uuid NOT NULL REFERENCES document_review(id) ON DELETE CASCADE,
  check_name    text NOT NULL,
  check_version text NOT NULL,
  status        text NOT NULL CHECK (status IN ('SUCCEEDED','FAILED')),
  stats         jsonb,
  error         text,
  started_at    timestamptz NOT NULL,
  finished_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX document_run_doc ON document_run(document_id, check_name, started_at DESC);

CREATE TABLE document_finding (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id       uuid NOT NULL REFERENCES document_run(id) ON DELETE CASCADE,
  document_id  uuid NOT NULL REFERENCES document_review(id) ON DELETE CASCADE,
  check_name   text NOT NULL,
  page_no      integer,
  severity     text NOT NULL CHECK (severity IN ('INFO','WARN','ERROR')),
  quote        text,
  message      text NOT NULL,
  suggestion   text,
  details      jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX document_finding_run ON document_finding(run_id, page_no);
