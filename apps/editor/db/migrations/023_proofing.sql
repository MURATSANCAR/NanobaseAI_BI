-- Final-read ("son okuma") checks: spelling, hyphenation, layout, object continuity, age
-- fit, name spelling, series canon, edition diff, text contradictions, imprint vs CRM.
-- Every check is a versioned run; a finding is a candidate for the editor, never a verdict
-- written into the book's knowledge. One queue item per check and book keeps the queue
-- readable however many findings a check produces.
SET search_path = ed, public;

CREATE TABLE proof_run (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id uuid NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  check_name    text NOT NULL,
  check_version text NOT NULL,
  status        text NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','FAILED','SKIPPED')),
  stats         jsonb NOT NULL DEFAULT '{}',
  error         text,
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz
);
CREATE INDEX proof_run_gen ON proof_run(generation_id, check_name, started_at DESC);

CREATE TABLE proof_finding (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id        uuid NOT NULL REFERENCES proof_run(id) ON DELETE CASCADE,
  generation_id uuid NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  check_name    text NOT NULL,
  page_no       int,
  severity      text NOT NULL CHECK (severity IN ('INFO','WARN','ERROR')),
  quote         text,               -- the text exactly as printed, when the finding is about text
  bbox          jsonb,              -- where on the page (0..1000), when known
  message       text NOT NULL,      -- what is wrong, in Turkish, for the editor
  suggestion    text,               -- what it probably should be, if the check knows
  details       jsonb NOT NULL DEFAULT '{}',
  status        text NOT NULL DEFAULT 'CANDIDATE' CHECK (status IN ('CANDIDATE','CONFIRMED','DISMISSED')),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX proof_finding_gen ON proof_finding(generation_id, check_name, page_no);

ALTER TABLE review_item ADD COLUMN proof_run_id uuid REFERENCES proof_run(id);
ALTER TABLE review_item DROP CONSTRAINT review_item_target_check;
ALTER TABLE review_item ADD CONSTRAINT review_item_target_check CHECK (
  claim_id IS NOT NULL OR contradiction_id IS NOT NULL OR page_role_page_no IS NOT NULL
  OR proof_run_id IS NOT NULL);
