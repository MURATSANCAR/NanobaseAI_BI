-- Özellik defteri (son okuma / görünüş sürekliliği).
-- Bir karakterin metinden ve resimden okunan görünüş özellikleri SAYFA SAYFA, her satır kendi
-- kanıtıyla: metin satırı bir alıntı (evidence.kind='TEXT'), resim satırı bir figür kutusu
-- (character_mention → evidence → visual_region.bbox). Süreklilik denetimleri bu defterden
-- beslenir, kitabı yeniden okumaz. Salt eklemedir: yanlış bir okuma silinmez, yeni okuyucu
-- sürümü yeni satır yazar (reader alanı); eski satırlar teşhis için kalır.
SET search_path = ed, public;

CREATE TABLE character_attribute (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id  uuid NOT NULL REFERENCES generation(id),
  character_id   uuid NOT NULL REFERENCES character(id),
  page_no        int  NOT NULL,
  kind           text NOT NULL,             -- proofing._attributes.KINDS anahtarı (SAC_RENGI, GOZLUK, ...)
  value          text NOT NULL,             -- o türün kapalı kümesinden; BELIRSIZ de kaydedilir
  source         text NOT NULL CHECK (source IN ('TEXT','IMAGE')),
  confidence     real NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  evidence_id    uuid NOT NULL REFERENCES evidence(id),   -- TEXT: alıntı kanıtı; IMAGE: figürün görsel kanıtı
  mention_id     uuid REFERENCES character_mention(id),   -- IMAGE: okunan figür
  bbox           jsonb,                     -- IMAGE: figür kutusu [x0,y0,x1,y1] 0..1000 (kopya, hızlı okuma için)
  quote          text,                      -- TEXT: sayfadaki kelimesi kelimesine alıntı
  reader         text NOT NULL,             -- okuyucu kimliği: prompt adı@sürümü (idempotenlik anahtarı)
  readings       jsonb NOT NULL DEFAULT '[]',   -- değeri veren bağımsız okumalar (oylama izi)
  model_call_ids bigint[] NOT NULL DEFAULT '{}',
  created_at     timestamptz NOT NULL DEFAULT now(),
  CHECK (source <> 'TEXT'  OR (quote IS NOT NULL AND length(btrim(quote)) > 0)),
  CHECK (source <> 'IMAGE' OR (mention_id IS NOT NULL AND bbox IS NOT NULL))
);
CREATE INDEX character_attribute_gen    ON character_attribute(generation_id, character_id, kind, page_no);
CREATE INDEX character_attribute_reader ON character_attribute(generation_id, source, reader);
CREATE TRIGGER character_attribute_append_only BEFORE UPDATE OR DELETE ON character_attribute
  FOR EACH ROW EXECUTE FUNCTION forbid_change();

-- Ne okunduğunun kaydı: özellik vermeyen bir sayfa/figür de "okundu" sayılır, yoksa her koşuda
-- yeniden okunurdu. TEXT: sayfa başına bir satır (mention_id boş); IMAGE: figür başına bir satır.
CREATE TABLE character_attribute_read (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id  uuid NOT NULL REFERENCES generation(id),
  source         text NOT NULL CHECK (source IN ('TEXT','IMAGE')),
  reader         text NOT NULL,
  page_no        int  NOT NULL,
  mention_id     uuid REFERENCES character_mention(id),
  character_id   uuid REFERENCES character(id),
  readings       jsonb NOT NULL DEFAULT '[]',   -- ham okumalar (IMAGE: her oyun cevabı)
  model_call_ids bigint[] NOT NULL DEFAULT '{}',
  created_at     timestamptz NOT NULL DEFAULT now(),
  CHECK (source <> 'IMAGE' OR mention_id IS NOT NULL)
);
CREATE UNIQUE INDEX character_attribute_read_key ON character_attribute_read(
  generation_id, source, reader, page_no,
  COALESCE(mention_id, '00000000-0000-0000-0000-000000000000'::uuid));
