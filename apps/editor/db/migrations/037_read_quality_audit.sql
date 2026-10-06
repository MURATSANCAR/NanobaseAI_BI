-- Okuma kalite denetimi (editor/read_audit.py, kullanıcı isteği 2026-10-06): her okuma bitince (iş akışının
-- «quality-audit-v1» adımı) ya da toplu komutla (`python -m editor.quality audit --all-read --fix`) yapılan denetimin
-- kaydı. Her koşu bir satır: kontrollerin sonucu, ilk bulgular, düzeltmelerden sonra kalan bulgular, yapılan
-- düzeltmeler ve durum. Kitap Eczanesi kitabın en yeni nesline ait en yeni satırı rozet (Temiz / Düzeltildi /
-- Gözden geçir) ve bulgu listesi olarak gösterir. Kuru komut koşusu yazmaz. Yapan her zaman «ZEKİ AI».
SET search_path = ed, public;
CREATE TABLE IF NOT EXISTS read_quality_audit (
  id            bigserial PRIMARY KEY,
  generation_id uuid NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  job_id        uuid,
  book_id       uuid,
  origin        text NOT NULL,                    -- WORKFLOW | COMMAND
  status        text NOT NULL,                    -- CLEAN | FIXED | REVIEW | REREAD
  rounds        int NOT NULL DEFAULT 1,           -- denetim sayısı (ilk + her düzeltme turundan sonra)
  checks        jsonb NOT NULL DEFAULT '{}',      -- kontrol adı → tamam/sorun; «_ask»: duman testinin soruları
  findings      jsonb NOT NULL DEFAULT '[]',      -- ilk denetimin bulguları
  remaining     jsonb NOT NULL DEFAULT '[]',      -- son denetimin bulguları (gözden geçir kuyruğu)
  fixes         jsonb NOT NULL DEFAULT '[]',      -- uygulanan eylemler, sonuçlarıyla
  version       text NOT NULL,
  actor         text NOT NULL DEFAULT 'ZEKİ AI',
  code_version  text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (origin IN ('WORKFLOW','COMMAND')),
  CHECK (status IN ('CLEAN','FIXED','REVIEW','REREAD'))
);
CREATE INDEX IF NOT EXISTS read_quality_audit_book ON read_quality_audit (book_id, created_at DESC);
CREATE INDEX IF NOT EXISTS read_quality_audit_generation ON read_quality_audit (generation_id, created_at DESC);
