-- Editör kararının aynı kitabın yeniden okumasına taşınması (docs/son-okuma/README.md «Aynı kitapta hatırlama»).
-- Taşıma OKUMADA yapılır (kart servisi, proofing/_carry.py): önceki okumadaki geçerli karar aynı bulguya
-- gösterilir, bu tabloya kendiliğinden hiçbir satır yazılmaz. Bu göç yalnız editörün taşınan karara verdiği
-- cevabı kaydedebilmek için:
--   * carried_from — editör, ekranda önceki okumadan gelmiş bir kararı gördüğü bulguya karar yazdıysa (onayladı,
--     değiştirdi ya da geri aldı) o kaynak karar. İsabet sayımında aynı kuralın (ad+sürüm) kaynak kararı,
--     onu onaylayan/değiştiren karar varken ikinci kez sayılmaz.
--   * verdict 'CLEAR' — «geri al»: bulgunun kararı yok (taşınan karar bu bulguya uygulanmaz). İsabete girmez;
--     sonraki okumalarda bu bulgunun en yeni kararı CLEAR olduğu için taşıma da durur.
-- Salt ekleme (forbid_change tetikleyicisi) değişmez.
SET search_path = ed, public;

ALTER TABLE proof_decision ADD COLUMN carried_from uuid REFERENCES proof_decision(id);

ALTER TABLE proof_decision DROP CONSTRAINT proof_decision_verdict_check;
ALTER TABLE proof_decision ADD CONSTRAINT proof_decision_verdict_check
  CHECK (verdict IN ('ACCEPT','REJECT','CLEAR'));
ALTER TABLE proof_decision DROP CONSTRAINT proof_decision_check;
ALTER TABLE proof_decision ADD CONSTRAINT proof_decision_check
  CHECK ((verdict = 'REJECT' AND reason_code IS NOT NULL) OR (verdict IN ('ACCEPT','CLEAR') AND reason_code IS NULL));

CREATE INDEX proof_decision_carried ON proof_decision(carried_from) WHERE carried_from IS NOT NULL;
