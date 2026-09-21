-- "Accepted" has to be sayable. Until now every generation carried the blocker
-- INDEPENDENT_SEMANTIC_ACCEPTANCE_NOT_RECORDED and nothing could record one, so the
-- readiness gate could only ever answer no. An acceptance is an editor's decision about ONE
-- validated revision: it names who, and which remaining blockers were knowingly waived.
-- A later correction moves the revision on and the acceptance no longer applies.
SET search_path = ed, public;
CREATE TABLE semantic_acceptance (
  id            bigserial PRIMARY KEY,
  generation_id uuid NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  revision      bigint NOT NULL,
  accepted_by   text NOT NULL CHECK (length(trim(accepted_by)) > 0),
  note          text NOT NULL DEFAULT '',
  waived        text[] NOT NULL DEFAULT '{}',
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (generation_id, revision)
);
CREATE FUNCTION semantic_acceptance_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'semantic_acceptance is append-only'; END $$;
CREATE TRIGGER semantic_acceptance_no_change BEFORE UPDATE OR DELETE ON semantic_acceptance
  FOR EACH ROW EXECUTE FUNCTION semantic_acceptance_immutable();
