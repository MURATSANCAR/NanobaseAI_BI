-- Aynı istek önbelleği (editor.llm.Llm._cached): sıcaklık 0 çağrı, aynı request_digest'le başarılı bir kayıt varsa
-- modele gitmez. Arama digest üzerinden; yalnız başarılı kayıtlar (2026-10-06: 759 bin satır, 8,4 GB tablo).
CREATE INDEX IF NOT EXISTS model_call_digest_ok ON ed.model_call (request_digest) WHERE ok;
