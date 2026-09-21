SET search_path=ed,public;
-- A validator records its own canonical changes separately from concurrent
-- corrections. Freeze refuses any intervening change by another writer.
ALTER TABLE knowledge_change ADD COLUMN writer_token text
 DEFAULT NULLIF(current_setting('editor.validation_token',true),'');
