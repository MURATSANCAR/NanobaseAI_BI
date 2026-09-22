-- Editörün son okuma bulgusuna kararı: «Doğru» (ACCEPT) ya da «Yanlış alarm» (REJECT).
-- İnsanın veri kaydıdır: uygulama kitabı düzeltmez, karar yalnız bulguya iliştirilir. Salt eklemedir:
-- yeni karar eskisini geçersiz kılar (bulgunun GEÇERLİ kararı = en yenisi), eski satırlar iz için kalır.
-- Kararlar kural başına (check_name + check_version) İSABET ölçüsünü besler:
--   isabet = ACCEPT / (ACCEPT + REJECT), her bulgunun yalnız geçerli kararı sayılarak, BÜTÜN kitaplarda;
-- kural sürümü değişince sayım o sürüm için sıfırdan başlar (docs/son-okuma/README.md).
SET search_path = ed, public;

CREATE TABLE proof_decision (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  finding_id    uuid NOT NULL REFERENCES proof_finding(id) ON DELETE CASCADE,
  generation_id uuid NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  check_name    text NOT NULL,             -- proof_run.check_name kopyası (hızlı sayım)
  check_version text NOT NULL,             -- proof_run.check_version kopyası: isabet sürüm başına ölçülür
  verdict       text NOT NULL CHECK (verdict IN ('ACCEPT','REJECT')),
  reason_code   text CHECK (reason_code IN ('TEXT_CORRECT','INTENDED_STYLE','DICTIONARY_GAP','WRONG_PAGE',
                                            'EXPLAINED_IN_TEXT','NOT_AN_ISSUE','OTHER')),
  note          text CHECK (note IS NULL OR length(note) <= 500),
  decided_by    text NOT NULL,             -- portal oturumundaki kullanıcı adı
  created_at    timestamptz NOT NULL DEFAULT now(),
  -- REJECT gerekçe ister; ACCEPT gerekçe taşımaz.
  CHECK ((verdict = 'REJECT' AND reason_code IS NOT NULL) OR (verdict = 'ACCEPT' AND reason_code IS NULL))
);
CREATE INDEX proof_decision_finding ON proof_decision(finding_id, created_at DESC);
CREATE INDEX proof_decision_check   ON proof_decision(generation_id, check_name);
CREATE INDEX proof_decision_rule    ON proof_decision(check_name, check_version);
CREATE TRIGGER proof_decision_append_only BEFORE UPDATE OR DELETE ON proof_decision
  FOR EACH ROW EXECUTE FUNCTION forbid_change();
