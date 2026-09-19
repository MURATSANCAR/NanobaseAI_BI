-- Editor Evidence Ledger (NIHAI-KARAR.md §1, §5, §7).
-- Book facts live here, never in Hermes' memory. Quality rules that can be
-- enforced by the database are enforced here, not left to prompts.

CREATE SCHEMA IF NOT EXISTS ed;
SET search_path = ed, public;

-- ---------------------------------------------------------------- books ---
CREATE TABLE book (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title        text NOT NULL,
  universe     text,                         -- series / universe key for canon
  age_group    text,                         -- declared target (publisher)
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- "Kitap ve içerik sürümünü oluşturur": one row per distinct file content.
CREATE TABLE book_version (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id      uuid NOT NULL REFERENCES book(id),
  sha256       text NOT NULL,
  file_path    text NOT NULL,
  file_bytes   bigint NOT NULL,
  page_count   int,
  pdf_meta     jsonb NOT NULL DEFAULT '{}',
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (book_id, sha256)
);

CREATE TABLE page (
  book_version_id uuid NOT NULL REFERENCES book_version(id),
  page_no      int  NOT NULL,                -- 1-based, physical PDF page
  width_pt     real,
  height_pt    real,
  text_layer_chars int NOT NULL DEFAULT 0,
  image_count  int NOT NULL DEFAULT 0,
  needs_ocr    boolean NOT NULL DEFAULT false,
  render_path  text,                         -- PNG under storage/
  render_dpi   int,
  PRIMARY KEY (book_version_id, page_no)
);

-- ----------------------------------------------------------- jobs/runs ---
CREATE TABLE analysis_job (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  book_version_id uuid NOT NULL REFERENCES book_version(id),
  profile      text NOT NULL DEFAULT 'full',
  status       text NOT NULL DEFAULT 'QUEUED'
               CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
  step         text,
  progress     jsonb NOT NULL DEFAULT '{}',
  workflow_id  text,
  requested_by text,
  error        text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  finished_at  timestamptz
);

-- "Eski analiz raporu üzerine yazılmaz; yeni generation_id oluşturulur."
CREATE TABLE generation (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id       uuid NOT NULL REFERENCES analysis_job(id),
  book_version_id uuid NOT NULL REFERENCES book_version(id),
  code_version text NOT NULL,
  model_manifest  jsonb NOT NULL DEFAULT '{}',   -- alias -> real model + revision
  prompt_manifest jsonb NOT NULL DEFAULT '{}',   -- prompt name -> version + sha256
  corrections_applied jsonb NOT NULL DEFAULT '[]',
  created_at   timestamptz NOT NULL DEFAULT now(),
  sealed_at    timestamptz                      -- set when the run finishes
);

-- "Model, prompt, sürüm ve kullanılan kaynaklar kaydedilir."
CREATE TABLE prompt (
  name         text NOT NULL,
  version      text NOT NULL,
  sha256       text NOT NULL,
  body         text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (name, version)
);

CREATE TABLE model_call (
  id           bigserial PRIMARY KEY,
  generation_id uuid REFERENCES generation(id),
  alias        text NOT NULL,
  real_model   text NOT NULL,
  revision     text NOT NULL,
  prompt_name  text,
  prompt_version text,
  pages        int[] NOT NULL DEFAULT '{}',
  request_digest text NOT NULL,
  request      jsonb,
  response     jsonb,
  prompt_tokens int,
  completion_tokens int,
  latency_ms   int,
  ok           boolean NOT NULL,
  error        text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX model_call_gen ON model_call(generation_id);

-- ----------------------------------------------------------- page data ---
CREATE TABLE page_text (
  generation_id uuid NOT NULL REFERENCES generation(id),
  book_version_id uuid NOT NULL,
  page_no      int NOT NULL,
  source       text NOT NULL CHECK (source IN ('TEXT_LAYER','OCR')),
  text         text NOT NULL,
  model_call_id bigint REFERENCES model_call(id),
  PRIMARY KEY (generation_id, page_no, source),
  FOREIGN KEY (book_version_id, page_no) REFERENCES page(book_version_id, page_no)
);

CREATE TABLE paragraph (
  generation_id uuid NOT NULL REFERENCES generation(id),
  page_no      int NOT NULL,
  idx          int NOT NULL,                 -- 1-based within page
  text         text NOT NULL,
  source       text NOT NULL,
  PRIMARY KEY (generation_id, page_no, idx)
);

CREATE TABLE visual_region (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  page_no      int NOT NULL,
  label        text NOT NULL,                -- short label from the vision model
  kind         text NOT NULL,                -- character / object / scene / text
  bbox         jsonb,                        -- [x0,y0,x1,y1] normalised 0..1000
  description  text,
  model_call_id bigint REFERENCES model_call(id)
);
CREATE INDEX visual_region_page ON visual_region(generation_id, page_no);

CREATE TABLE page_scan (
  generation_id uuid NOT NULL REFERENCES generation(id),
  page_no      int NOT NULL,
  pass         text NOT NULL CHECK (pass IN ('FAST','DEEP')),
  alias        text NOT NULL,
  result       jsonb NOT NULL,
  uncertain    boolean NOT NULL DEFAULT false,
  uncertainty_reasons text[] NOT NULL DEFAULT '{}',
  model_call_id bigint REFERENCES model_call(id),
  PRIMARY KEY (generation_id, page_no, pass)
);

-- ----------------------------------------------------- evidence ledger ---
-- Every claim points at one or more evidence rows; every evidence row points
-- at a page and at least one of: paragraph, visual region, event.
CREATE TABLE evidence (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  page_no      int NOT NULL,
  paragraph_idx int,
  region_id    uuid REFERENCES visual_region(id),
  event_id     uuid,
  kind         text NOT NULL CHECK (kind IN ('TEXT','VISUAL','EVENT')),
  quote        text NOT NULL CHECK (length(btrim(quote)) > 0),
  quote_verified boolean NOT NULL DEFAULT false,   -- quote found verbatim in page text
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX evidence_gen_page ON evidence(generation_id, page_no);

CREATE TABLE claim (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  kind         text NOT NULL CHECK (kind IN (
                 'CHARACTER','CHARACTER_IDENTITY','EVENT','EMOTION','THEME',
                 'SUMMARY','VISUAL_SCENE','VISUAL_CONTINUITY','TEXT_VISUAL_MISMATCH',
                 'CANON','AGE_GROUP','PUBLISHER_DECISION','ANSWER')),
  subject      text,
  claim        text NOT NULL CHECK (length(btrim(claim)) > 0),
  source_pages int[] NOT NULL CHECK (cardinality(source_pages) > 0),
  payload      jsonb NOT NULL DEFAULT '{}',
  confidence   real NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  status       text NOT NULL DEFAULT 'CANDIDATE' CHECK (status IN (
                 'CANDIDATE','VERIFIED','NEEDS_REVIEW','REJECTED',
                 'EDITOR_APPROVED','EDITOR_REJECTED','EDITOR_CORRECTED')),
  needs_editor_review boolean NOT NULL DEFAULT false,
  created_by   text NOT NULL,               -- step / agent / alias
  model_call_id bigint REFERENCES model_call(id),
  critic_note  text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX claim_gen_kind ON claim(generation_id, kind);

CREATE TABLE claim_evidence (
  claim_id     uuid NOT NULL REFERENCES claim(id),
  evidence_id  uuid NOT NULL REFERENCES evidence(id),
  PRIMARY KEY (claim_id, evidence_id)
);

-- "Kaynaksız iddia üretilemez." Checked at COMMIT so a claim and its
-- evidence links can be written in one transaction.
CREATE FUNCTION claim_requires_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM ed.claim_evidence WHERE claim_id = NEW.id) THEN
    RAISE EXCEPTION 'claim % has no evidence (Kaynaksız iddia üretilemez)', NEW.id
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER claim_requires_evidence
  AFTER INSERT ON claim DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION claim_requires_evidence();

-- Claim content is immutable; only status/confidence/review fields move.
CREATE FUNCTION claim_content_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.claim IS DISTINCT FROM OLD.claim OR NEW.kind IS DISTINCT FROM OLD.kind
     OR NEW.subject IS DISTINCT FROM OLD.subject OR NEW.payload IS DISTINCT FROM OLD.payload
     OR NEW.source_pages IS DISTINCT FROM OLD.source_pages
     OR NEW.generation_id IS DISTINCT FROM OLD.generation_id THEN
    RAISE EXCEPTION 'claim content is immutable; write a new generation instead';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER claim_content_immutable BEFORE UPDATE ON claim
  FOR EACH ROW EXECUTE FUNCTION claim_content_immutable();

-- ----------------------------------------------------------- knowledge ---
-- "Belirsiz karakter kesin kimlik olarak kaydedilemez."
CREATE TABLE character (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  canonical_name text NOT NULL,
  aliases      text[] NOT NULL DEFAULT '{}',
  description  text,
  appearance   jsonb NOT NULL DEFAULT '{}',
  identity_status text NOT NULL DEFAULT 'CANDIDATE'
               CHECK (identity_status IN ('CANDIDATE','UNCERTAIN','CONFIRMED')),
  identity_confidence real NOT NULL CHECK (identity_confidence BETWEEN 0 AND 1),
  first_page   int,
  claim_id     uuid REFERENCES claim(id),
  CHECK (identity_status <> 'CONFIRMED' OR identity_confidence >= 0.85)
);

CREATE TABLE character_mention (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  page_no      int NOT NULL,
  surface_name text,                         -- as written / as seen
  character_id uuid REFERENCES character(id),
  via          text NOT NULL CHECK (via IN ('TEXT','VISUAL','BOTH')),
  appearance   jsonb NOT NULL DEFAULT '{}',
  resolution   text NOT NULL DEFAULT 'UNRESOLVED'
               CHECK (resolution IN ('UNRESOLVED','UNCERTAIN','RESOLVED')),
  confidence   real NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  evidence_id  uuid NOT NULL REFERENCES evidence(id),
  CHECK (resolution <> 'RESOLVED' OR (character_id IS NOT NULL AND confidence >= 0.75))
);
CREATE INDEX character_mention_gen ON character_mention(generation_id, page_no);

-- "Plan, hayal veya şaka gerçekleşmiş olay sayılmaz."
CREATE TABLE event (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  page_from    int NOT NULL,
  page_to      int NOT NULL,
  summary      text NOT NULL,
  modality     text NOT NULL CHECK (modality IN (
                 'REALIZED','PLAN','DREAM','IMAGINATION','JOKE','LIE',
                 'HYPOTHETICAL','MEMORY','UNCERTAIN')),
  participants text[] NOT NULL DEFAULT '{}',
  importance   real NOT NULL DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
  story_order  int,                          -- set only for REALIZED events
  merged_into  uuid REFERENCES event(id),
  confidence   real NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  claim_id     uuid REFERENCES claim(id),
  CHECK (story_order IS NULL OR modality IN ('REALIZED','MEMORY')),
  CHECK (page_from <= page_to)
);
ALTER TABLE evidence ADD CONSTRAINT evidence_event_fk
  FOREIGN KEY (event_id) REFERENCES event(id);

CREATE VIEW timeline AS
  SELECT * FROM event
   WHERE modality IN ('REALIZED','MEMORY') AND merged_into IS NULL;

CREATE TABLE emotion (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  character_id uuid REFERENCES character(id),
  character_name text NOT NULL,
  page_no      int NOT NULL,
  emotion      text NOT NULL,
  intensity    real NOT NULL CHECK (intensity BETWEEN 0 AND 1),
  trigger      text,
  confidence   real NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  claim_id     uuid REFERENCES claim(id)
);

CREATE TABLE contradiction (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  kind         text NOT NULL,                -- TEXT_VISUAL, CONTINUITY, TIMELINE, CANON, IDENTITY
  description  text NOT NULL,
  pages        int[] NOT NULL,
  claim_ids    uuid[] NOT NULL DEFAULT '{}',
  -- "Görsel-metinsel uyuşmazlık doğrudan hata değil, aday bulgu olur."
  status       text NOT NULL DEFAULT 'CANDIDATE'
               CHECK (status IN ('CANDIDATE','NEEDS_REVIEW','EDITOR_CONFIRMED','EDITOR_DISMISSED')),
  confidence   real NOT NULL CHECK (confidence BETWEEN 0 AND 1)
);

-- ------------------------------------------------------ editor / canon ---
CREATE TABLE review_item (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  claim_id     uuid REFERENCES claim(id),
  contradiction_id uuid REFERENCES contradiction(id),
  reason       text NOT NULL,
  priority     int NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
  status       text NOT NULL DEFAULT 'OPEN'
               CHECK (status IN ('OPEN','APPROVED','REJECTED','CORRECTED')),
  decided_by   text,
  decision     jsonb,
  created_at   timestamptz NOT NULL DEFAULT now(),
  decided_at   timestamptz,
  CHECK (claim_id IS NOT NULL OR contradiction_id IS NOT NULL),
  CHECK (status = 'OPEN' OR decided_by IS NOT NULL)
);

-- "Editör düzeltmesi sonraki analizlere aktarılır." Keyed by book, not by
-- generation, so every later run of the same book loads it.
CREATE TABLE editor_correction (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id      uuid NOT NULL REFERENCES book(id),
  review_item_id uuid REFERENCES review_item(id),
  target_kind  text NOT NULL,                -- CHARACTER_IDENTITY, EVENT_MODALITY, CLAIM, ...
  target_key   text NOT NULL,                -- e.g. character name, event summary
  correction   jsonb NOT NULL,
  editor       text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- "Editör onayı olmadan kanonu değiştirme."
CREATE TABLE canon_entry (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  universe     text NOT NULL,
  kind         text NOT NULL,                -- CHARACTER, PLACE, RULE, RELATION
  key          text NOT NULL,
  value        jsonb NOT NULL,
  source_claim uuid REFERENCES claim(id),
  approved_by  text NOT NULL CHECK (length(btrim(approved_by)) > 0),
  approved_at  timestamptz NOT NULL DEFAULT now(),
  superseded_by uuid REFERENCES canon_entry(id)
);

-- --------------------------------------------------- reports / quality ---
CREATE TABLE report (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  kind         text NOT NULL,                -- ANALYSIS, EDITOR, PUBLISHER
  content      jsonb NOT NULL,
  markdown     text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only (yeni generation_id oluşturun)', TG_TABLE_NAME;
END $$;
CREATE TRIGGER report_append_only BEFORE UPDATE OR DELETE ON report
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER evidence_append_only BEFORE UPDATE OR DELETE ON evidence
  FOR EACH ROW EXECUTE FUNCTION forbid_change();

CREATE TABLE regression_run (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id),
  suite        text NOT NULL,
  passed       boolean NOT NULL,
  results      jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
