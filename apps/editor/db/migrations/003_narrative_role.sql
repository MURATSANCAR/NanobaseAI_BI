-- Importance is relative to the whole book, so it is decided by the director
-- over the merged timeline (not by a vision model looking at one page).
SET search_path = ed, public;
ALTER TABLE event ADD COLUMN narrative_role text
  CHECK (narrative_role IN ('SETUP','INCITING','TURNING_POINT','CLIMAX','RESOLUTION','ORDINARY'));
-- the view was created with SELECT *, which froze its column list
DROP VIEW timeline;
CREATE VIEW timeline AS
  SELECT * FROM event WHERE modality IN ('REALIZED','MEMORY') AND merged_into IS NULL;
