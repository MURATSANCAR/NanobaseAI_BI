-- Page-role review is a first-class target, not a fabricated factual claim.
SET search_path = ed, public;
ALTER TABLE review_item ADD COLUMN page_role_page_no integer;
ALTER TABLE review_item ADD CONSTRAINT review_item_page_role_fk
  FOREIGN KEY (generation_id, page_role_page_no) REFERENCES page_role(generation_id, page_no);
ALTER TABLE review_item DROP CONSTRAINT review_item_check;
ALTER TABLE review_item ADD CONSTRAINT review_item_target_check CHECK (
  claim_id IS NOT NULL OR contradiction_id IS NOT NULL OR page_role_page_no IS NOT NULL);
CREATE UNIQUE INDEX review_item_open_page_role ON review_item(generation_id, page_role_page_no)
  WHERE status='OPEN' AND page_role_page_no IS NOT NULL;
