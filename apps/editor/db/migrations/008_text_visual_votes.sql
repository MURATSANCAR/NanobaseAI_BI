-- A text-visual finding must survive independent re-readings of the same page (one
-- reading of one page is not stable: the same model reports it in one run and not in
-- the next). One row per page: what was proposed, how each proposal was voted.
SET search_path = ed, public;
CREATE TABLE text_visual_check (
  generation_id uuid NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  page_no       int  NOT NULL,
  proposed      int  NOT NULL,
  confirmed     int  NOT NULL,
  detail        jsonb NOT NULL DEFAULT '[]',
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (generation_id, page_no)
);
