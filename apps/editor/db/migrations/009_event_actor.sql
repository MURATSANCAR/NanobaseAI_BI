-- Who did what. The extractor names an event's participants in one free-text reading of a
-- four-page chunk, with no probability and no link to the resolved characters. Here every
-- (event, character) pair gets its own closed-set reading: the character DOES the action,
-- only TAKES PART in it, or is ABSENT, with the probability of each read from the model's
-- token distribution. One row per pair, so a retried activity writes nothing twice.
SET search_path = ed, public;
CREATE TABLE event_actor (
  event_id      uuid NOT NULL REFERENCES event(id),
  character_id  uuid NOT NULL REFERENCES character(id),
  generation_id uuid NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  p_actor       real NOT NULL CHECK (p_actor BETWEEN 0 AND 1),
  p_involved    real NOT NULL CHECK (p_involved BETWEEN 0 AND 1),
  p_absent      real NOT NULL CHECK (p_absent BETWEEN 0 AND 1),
  -- UNCERTAIN: no reading reached the configured probability; never shown as a fact
  role          text NOT NULL CHECK (role IN ('ACTOR','INVOLVED','ABSENT','UNCERTAIN')),
  listed_by_extractor boolean NOT NULL,     -- was this character among event.participants
  model_call_id bigint REFERENCES model_call(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, character_id)
);
CREATE INDEX event_actor_gen ON event_actor(generation_id, role);
