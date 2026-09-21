-- The adjudicator's answer for one cluster: same figures, same prompt version -> same
-- question, asked once. A re-run (new threshold, new rule elsewhere) reuses it.
SET search_path = ed, public;
CREATE TABLE cluster_verdict (
  generation_id uuid NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  members_key   text NOT NULL,
  prompt        text NOT NULL,
  verdict       jsonb NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (generation_id, members_key, prompt)
);
