-- What kind of being a character is (from the text) gates which drawn figures can be it.
SET search_path = ed, public;
ALTER TABLE character ADD COLUMN kind text NOT NULL DEFAULT 'UNKNOWN'
  CHECK (kind IN ('HUMAN_CHILD','HUMAN_ADULT','ANIMAL','ROBOT_OR_MACHINE','FANTASY_CREATURE','OTHER','UNKNOWN'));
