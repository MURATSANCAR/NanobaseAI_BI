SET search_path=ed,public;

ALTER TABLE generation_state ADD COLUMN producer_completed boolean NOT NULL DEFAULT false;
ALTER TABLE generation_state ADD COLUMN validated_revision bigint;
ALTER TABLE rebuild_request ADD COLUMN attempts integer NOT NULL DEFAULT 0;
ALTER TABLE rebuild_request ADD COLUMN attempted_revision bigint;
ALTER TABLE rebuild_request ADD COLUMN retry_after timestamptz;
ALTER TABLE rebuild_request ADD COLUMN last_error text;
ALTER TABLE rebuild_request ADD COLUMN consumer_backend_pid integer;
ALTER TABLE rebuild_request ADD COLUMN consumer_backend_start timestamptz;

-- Immutable input and output versions. Public reads follow only a current pointer.
CREATE TABLE knowledge_snapshot (
 generation_id uuid NOT NULL REFERENCES generation(id),
 revision bigint NOT NULL,
 input_digest text NOT NULL,
 content jsonb NOT NULL,
 validation jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(generation_id,revision,input_digest)
);
CREATE TABLE artifact_version (
 generation_id uuid NOT NULL REFERENCES generation(id),
 kind text NOT NULL REFERENCES artifact_definition(kind),
 build_key text NOT NULL,
 input_revision bigint NOT NULL,
 input_digest text NOT NULL,
 content jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(generation_id,kind,build_key),
 FOREIGN KEY(generation_id,input_revision,input_digest)
   REFERENCES knowledge_snapshot(generation_id,revision,input_digest)
);
CREATE FUNCTION immutable_output_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Output and input versions are immutable'; END $$;
CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON knowledge_snapshot
 FOR EACH ROW EXECUTE FUNCTION immutable_output_version();
CREATE TRIGGER immutable_artifact BEFORE UPDATE OR DELETE ON artifact_version
 FOR EACH ROW EXECUTE FUNCTION immutable_output_version();

-- This also catches invalidation initiated by any existing knowledge trigger.
CREATE FUNCTION output_validation_reset() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.knowledge_revision <> OLD.knowledge_revision THEN
  NEW.validated_revision := NULL;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER output_validation_reset BEFORE UPDATE ON generation_state
 FOR EACH ROW EXECUTE FUNCTION output_validation_reset();

-- Review/contradiction changes affect report validity as well as acceptance.
CREATE TRIGGER foundation_track_knowledge BEFORE INSERT OR UPDATE OR DELETE ON review_item
 FOR EACH ROW EXECUTE FUNCTION foundation_track_knowledge();
CREATE TRIGGER foundation_track_knowledge BEFORE INSERT OR UPDATE OR DELETE ON contradiction
 FOR EACH ROW EXECUTE FUNCTION foundation_track_knowledge();

-- An event correction invalidates the old actor reading as part of the same tx.
CREATE FUNCTION reset_changed_event_actors() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.summary,NEW.claim_id,NEW.participants,NEW.modality,NEW.page_from,NEW.page_to)
    IS DISTINCT FROM (OLD.summary,OLD.claim_id,OLD.participants,OLD.modality,OLD.page_from,OLD.page_to) THEN
  DELETE FROM ed.event_actor WHERE event_id=NEW.id;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER reset_changed_event_actors AFTER UPDATE ON event
 FOR EACH ROW EXECUTE FUNCTION reset_changed_event_actors();
CREATE FUNCTION reset_changed_character_actors() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.canonical_name,NEW.aliases,NEW.description,NEW.identity_status)
    IS DISTINCT FROM (OLD.canonical_name,OLD.aliases,OLD.description,OLD.identity_status) THEN
  DELETE FROM ed.event_actor WHERE generation_id=NEW.generation_id;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER reset_changed_character_actors AFTER UPDATE ON character
 FOR EACH ROW EXECUTE FUNCTION reset_changed_character_actors();

CREATE VIEW current_artifact AS
 SELECT a.generation_id,a.kind,a.build_key,a.input_revision,v.input_digest,v.content,v.created_at
 FROM derived_artifact a JOIN generation_state s USING(generation_id)
 JOIN artifact_version v ON v.generation_id=a.generation_id AND v.kind=a.kind AND v.build_key=a.build_key
 WHERE a.state='READY' AND a.input_revision=s.knowledge_revision
   AND s.validated_revision=s.knowledge_revision AND v.input_revision=a.input_revision;

CREATE TRIGGER foundation_track_knowledge BEFORE INSERT OR UPDATE OR DELETE ON text_visual_check
 FOR EACH ROW EXECUTE FUNCTION foundation_track_knowledge();
CREATE TRIGGER foundation_track_knowledge BEFORE INSERT OR UPDATE OR DELETE ON regression_run
 FOR EACH ROW EXECUTE FUNCTION foundation_track_knowledge();

CREATE FUNCTION guard_output_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s ed.generation_state%ROWTYPE; rev bigint;
BEGIN
 IF (SELECT maintenance FROM ed.runtime_control WHERE singleton) THEN
  RAISE EXCEPTION 'EDITOR_MAINTENANCE: output writes are disabled';
 END IF;
 SELECT * INTO s FROM ed.generation_state WHERE generation_id=NEW.generation_id FOR UPDATE;
 IF s.origin<>'TRACKED' OR NOT s.producer_completed OR EXISTS
   (SELECT 1 FROM ed.generation WHERE id=NEW.generation_id AND sealed_at IS NOT NULL) THEN
  RAISE EXCEPTION 'Only completed producers in an open tracked generation may build outputs';
 END IF;
 rev := CASE WHEN TG_TABLE_NAME='knowledge_snapshot' THEN (to_jsonb(NEW)->>'revision')::bigint
             ELSE (to_jsonb(NEW)->>'input_revision')::bigint END;
 IF rev<>s.knowledge_revision OR (TG_TABLE_NAME='artifact_version' AND s.validated_revision IS DISTINCT FROM rev) THEN
  RAISE EXCEPTION 'Output input revision is stale or unvalidated';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_output_version BEFORE INSERT ON knowledge_snapshot
 FOR EACH ROW EXECUTE FUNCTION guard_output_version();
CREATE TRIGGER guard_output_version BEFORE INSERT ON artifact_version
 FOR EACH ROW EXECUTE FUNCTION guard_output_version();
