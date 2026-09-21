SET search_path TO ed, public;

-- A repaired writer receives a fresh bounded budget; restarting the same
-- writer does not. Knowledge revisions and model-profile fences still apply.
ALTER TABLE rebuild_request ADD COLUMN attempted_code_version text;
