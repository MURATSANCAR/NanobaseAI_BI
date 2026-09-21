-- Foundation only. Legacy generations remain unassessed; no book is reanalysed.
SET search_path = ed, public;

-- The live preflight found no duplicate job IDs; refuse migration if one appears.
CREATE UNIQUE INDEX generation_job_once ON generation(job_id);

CREATE TABLE runtime_control (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  maintenance boolean NOT NULL DEFAULT true,
  reason text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO runtime_control(reason) VALUES ('User requested analysis stop; foundation preparation');

CREATE TABLE generation_state (
  generation_id uuid PRIMARY KEY REFERENCES generation(id),
  knowledge_revision bigint NOT NULL DEFAULT 0 CHECK (knowledge_revision >= 0),
  origin text NOT NULL CHECK (origin IN ('LEGACY_UNASSESSED','TRACKED')),
  coverage_status text NOT NULL DEFAULT 'NOT_EVALUATED'
    CHECK (coverage_status IN ('NOT_EVALUATED','PARTIAL','PASSED','FAILED')),
  semantic_status text NOT NULL DEFAULT 'NOT_EVALUATED'
    CHECK (semantic_status IN ('NOT_EVALUATED','PASSED','FAILED','NEEDS_REVIEW')),
  publication_status text NOT NULL DEFAULT 'BLOCKED'
    CHECK (publication_status IN ('BLOCKED','READY','PUBLISHED')),
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO generation_state(generation_id,origin) SELECT id,'LEGACY_UNASSESSED' FROM generation;

CREATE TABLE artifact_definition (
  kind text PRIMARY KEY,
  depends_on text[] NOT NULL
);
INSERT INTO artifact_definition VALUES
 ('chapter_summaries',ARRAY['knowledge']),
 ('book_summary',ARRAY['knowledge','chapter_summaries']),
 ('report',ARRAY['knowledge','chapter_summaries','book_summary']),
 ('search_index',ARRAY['knowledge']),
 ('catalog',ARRAY['knowledge','book_summary']);

CREATE TABLE derived_artifact (
  generation_id uuid NOT NULL REFERENCES generation(id),
  kind text NOT NULL REFERENCES artifact_definition(kind),
  state text NOT NULL DEFAULT 'MISSING'
    CHECK (state IN ('UNTRACKED','MISSING','STALE','BUILDING','READY','FAILED')),
  input_revision bigint,
  build_key text,
  output_reference jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(generation_id,kind),
  CHECK (state <> 'READY' OR (input_revision IS NOT NULL AND build_key IS NOT NULL
                             AND output_reference IS NOT NULL))
);
INSERT INTO derived_artifact(generation_id,kind,state)
 SELECT g.id,d.kind,'UNTRACKED' FROM generation g CROSS JOIN artifact_definition d;

CREATE TABLE knowledge_change (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  generation_id uuid NOT NULL REFERENCES generation(id),
  revision bigint NOT NULL,
  source_table text NOT NULL,
  operation text NOT NULL,
  before_value jsonb,
  after_value jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(generation_id,revision)
);

-- One coalescing queue item per generation. Changes while a build is running
-- advance requested_revision; finishing an older build cannot acknowledge them.
CREATE TABLE rebuild_request (
  generation_id uuid PRIMARY KEY REFERENCES generation(id),
  requested_revision bigint NOT NULL,
  completed_revision bigint NOT NULL DEFAULT -1,
  reason text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (completed_revision <= requested_revision)
);

CREATE TABLE operation_receipt (
  generation_id uuid NOT NULL REFERENCES generation(id),
  stage text NOT NULL,
  input_digest text NOT NULL,
  result jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(generation_id,stage,input_digest)
);

CREATE FUNCTION foundation_job_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IN ('QUEUED','RUNNING') AND
     (SELECT maintenance FROM ed.runtime_control WHERE singleton) THEN
    RAISE EXCEPTION 'EDITOR_MAINTENANCE: new analysis is disabled';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER foundation_job_guard BEFORE INSERT OR UPDATE ON analysis_job
 FOR EACH ROW EXECUTE FUNCTION foundation_job_guard();

CREATE FUNCTION foundation_generation_init() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT maintenance FROM ed.runtime_control WHERE singleton) THEN
    RAISE EXCEPTION 'EDITOR_MAINTENANCE: new generation is disabled';
  END IF;
  INSERT INTO ed.generation_state(generation_id,origin) VALUES (NEW.id,'TRACKED');
  INSERT INTO ed.derived_artifact(generation_id,kind)
    SELECT NEW.id,kind FROM ed.artifact_definition;
  RETURN NEW;
END $$;
CREATE TRIGGER foundation_generation_init AFTER INSERT ON generation
 FOR EACH ROW EXECUTE FUNCTION foundation_generation_init();

CREATE FUNCTION foundation_track_knowledge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  previous jsonb;
  current_value jsonb;
  gid uuid;
  rev bigint;
BEGIN
  IF TG_OP <> 'INSERT' THEN previous := to_jsonb(OLD); END IF;
  IF TG_OP <> 'DELETE' THEN current_value := to_jsonb(NEW); END IF;
  IF TG_OP = 'UPDATE' AND previous = current_value THEN RETURN NEW; END IF;
  gid := COALESCE(current_value->>'generation_id',previous->>'generation_id')::uuid;
  IF TG_TABLE_NAME = 'claim_evidence' THEN
    SELECT generation_id INTO gid FROM ed.claim
      WHERE id=COALESCE(current_value->>'claim_id',previous->>'claim_id')::uuid;
    IF TG_OP = 'UPDATE' AND previous->>'claim_id' IS DISTINCT FROM current_value->>'claim_id' THEN
      RAISE EXCEPTION 'claim_evidence claim_id is immutable';
    END IF;
    IF TG_OP <> 'DELETE' AND NOT EXISTS (SELECT 1 FROM ed.evidence
        WHERE id=(current_value->>'evidence_id')::uuid AND generation_id=gid) THEN
      RAISE EXCEPTION 'Claim and evidence must belong to the same generation';
    END IF;
  END IF;
  IF TG_OP = 'UPDATE' AND previous->>'generation_id' IS DISTINCT FROM current_value->>'generation_id' THEN
    RAISE EXCEPTION 'generation_id is immutable';
  END IF;
  IF (SELECT maintenance FROM ed.runtime_control WHERE singleton) THEN
    RAISE EXCEPTION 'EDITOR_MAINTENANCE: knowledge writes are disabled';
  END IF;
  IF EXISTS (SELECT 1 FROM ed.generation WHERE id=gid AND sealed_at IS NOT NULL) THEN
    RAISE EXCEPTION 'Sealed generation is immutable; create a new generation';
  END IF;
  -- Summaries, reports and answers are derived outputs, not canonical inputs.
  -- Their own artifact builds/invalidation use foundation.invalidate_dependents.
  IF TG_TABLE_NAME = 'claim' AND
     COALESCE(current_value->>'kind',previous->>'kind') IN
       ('SUMMARY','ANSWER','AGE_GROUP','PUBLISHER_DECISION') THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  UPDATE ed.generation_state SET knowledge_revision=knowledge_revision+1,
    coverage_status='NOT_EVALUATED', semantic_status='NOT_EVALUATED',
    publication_status='BLOCKED',updated_at=now()
    WHERE generation_id=gid RETURNING knowledge_revision INTO rev;
  IF rev IS NULL THEN RAISE EXCEPTION 'Missing generation state for %',gid; END IF;
  INSERT INTO ed.knowledge_change(generation_id,revision,source_table,operation,before_value,after_value)
    VALUES(gid,rev,TG_TABLE_NAME,TG_OP,previous,current_value);
  UPDATE ed.derived_artifact SET state='STALE',updated_at=now() WHERE generation_id=gid;
  INSERT INTO ed.rebuild_request(generation_id,requested_revision,reason)
    VALUES(gid,rev,TG_TABLE_NAME || ':' || TG_OP)
    ON CONFLICT(generation_id) DO UPDATE SET requested_revision=EXCLUDED.requested_revision,
      reason=EXCLUDED.reason,updated_at=now();
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;

DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['page_text','paragraph','page_role','page_scan','visual_region',
    'character','character_mention','event','emotion','event_actor','claim','evidence','claim_evidence'] LOOP
    EXECUTE format('CREATE TRIGGER foundation_track_knowledge BEFORE INSERT OR UPDATE OR DELETE ON ed.%I '
      'FOR EACH ROW EXECUTE FUNCTION ed.foundation_track_knowledge()',t);
  END LOOP;
END $$;

-- Explicit preview contract: accepted claim, same-generation evidence, real
-- source pages. It does not certify full-book coverage or editorial acceptance.
CREATE VIEW usable_claim AS
 SELECT c.* FROM claim c JOIN generation g ON g.id=c.generation_id
 WHERE c.status IN ('VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED')
   AND NOT c.needs_editor_review
   AND NOT EXISTS (SELECT 1 FROM unnest(c.source_pages) p
     WHERE NOT EXISTS (SELECT 1 FROM page WHERE book_version_id=g.book_version_id AND page_no=p))
   AND EXISTS (SELECT 1 FROM claim_evidence ce JOIN evidence e ON e.id=ce.evidence_id
     WHERE ce.claim_id=c.id AND e.generation_id=c.generation_id
       AND (e.quote_verified OR (e.kind='VISUAL' AND EXISTS
         (SELECT 1 FROM visual_region v WHERE v.id=e.region_id AND v.generation_id=c.generation_id))))
   AND NOT EXISTS (SELECT 1 FROM claim_evidence ce JOIN evidence e ON e.id=ce.evidence_id
     WHERE ce.claim_id=c.id AND (e.generation_id<>c.generation_id OR NOT EXISTS
       (SELECT 1 FROM page WHERE book_version_id=g.book_version_id AND page_no=e.page_no)));

-- A corrected claim with stale typed event fields is excluded until rebuilt.
CREATE VIEW usable_event AS
 SELECT e.* FROM event e JOIN usable_claim c ON c.id=e.claim_id AND c.generation_id=e.generation_id
 WHERE e.merged_into IS NULL AND e.summary=c.claim;

CREATE VIEW usable_emotion AS
 SELECT e.* FROM emotion e JOIN usable_claim c ON c.id=e.claim_id AND c.generation_id=e.generation_id
 WHERE e.character_id IS NOT NULL AND EXISTS
   (SELECT 1 FROM character ch WHERE ch.id=e.character_id AND ch.generation_id=e.generation_id)
   AND c.payload->>'emotion'=e.emotion
   AND COALESCE(c.payload->>'trigger','')=COALESCE(e.trigger,'')
   AND NOT (c.payload ? 'supersedes');
